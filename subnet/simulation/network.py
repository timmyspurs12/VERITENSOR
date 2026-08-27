"""In-process subnet runtime.

``SubnetNetwork`` is the object the API serves from. It holds miners,
validators, reputations, task records and the event bus, and exposes the two
operations the product is built around:

* ``step()``          – run one verification task end-to-end
* ``run_simulation()`` – run N tasks across V validators and M miners

Everything the dashboard displays is derived from this object. There is no
second, cosmetic data source.
"""

from __future__ import annotations

import asyncio
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from ..miner.profiles import PROFILES, MinerProfile, get_profile
from ..miner.simulated import SimulatedMiner
from ..protocol.messages import Category
from ..scoring.config import DEFAULT_CONFIG, MechanismConfig
from ..scoring.emissions import EmissionInput, EmissionResult, compute_emissions
from ..scoring.engine import aggregate_scores
from ..scoring.reputation import MinerReputation
from ..validator.events import EventBus
from ..validator.records import TaskRecord
from ..validator.strategies import STRATEGIES, ValidatorStrategy, get_strategy
from ..validator.validator import Validator

try:  # the bank lives outside the subnet package and is optional
    from benchmarks import register_benchmark_generators

    register_benchmark_generators()
except Exception:  # pragma: no cover - bank absent in a stripped deployment
    pass

MINER_CALLSIGNS = [
    "Alpha", "Tensor-X", "Neural", "Quanta", "Helios", "Vertex", "Onyx",
    "Kepler", "Aegis", "Nimbus", "Orion", "Ferrum", "Cobalt", "Lyra",
    "Zephyr", "Atlas", "Pyxis", "Solace", "Vanta", "Corvus", "Hydra",
    "Terra", "Umbra", "Vega", "Wisp", "Xenon", "Yotta", "Zenith",
    "Basalt", "Cinder", "Delve", "Ember", "Flint", "Grove", "Halcyon",
    "Ion", "Juno", "Kite", "Lumen", "Mesa", "Nova", "Opal", "Prism",
    "Quill", "Rook", "Slate", "Torus", "Ursa", "Volt", "Warden",
]

VALIDATOR_CALLSIGNS = ["Praxis", "Meridian", "Sentinel", "Arbiter", "Lattice",
                       "Beacon", "Custos"]

#: default population mix used when seeding the demo network
DEFAULT_MIX: List[tuple[str, float]] = [
    ("high_quality", 0.14), ("balanced", 0.20), ("fast", 0.16),
    ("specialist_code", 0.10), ("specialist_math", 0.10), ("weak", 0.12),
    ("hallucinating", 0.08), ("gaming", 0.06), ("unstable", 0.04),
]


@dataclass(slots=True)
class SimulationConfig:
    miners: int = 12
    validators: int = 3
    tasks: int = 60
    difficulty_mode: str = "adaptive"   # easy | normal | hard | adaptive
    seed: Optional[int] = None
    categories: Optional[List[str]] = None

    def difficulty_override(self) -> Optional[int]:
        return {"easy": 2, "normal": 5, "hard": 8}.get(self.difficulty_mode)


@dataclass(slots=True)
class EpochSnapshot:
    epoch: int
    timestamp: datetime
    tasks: int
    network_accuracy: float
    network_score: float
    mean_latency_ms: float
    emission_gini: float
    top_miner_uid: Optional[int]


class SubnetNetwork:
    """Local subnet runtime (SIMULATION mode)."""

    def __init__(self, config: MechanismConfig = DEFAULT_CONFIG,
                 seed: Optional[int] = 1337, mode: str = "simulation",
                 netuid: int = 47) -> None:
        self.config = config
        self.mode = mode
        self.netuid = netuid
        self.seed = seed
        self.rng = random.Random(seed)
        self.bus = EventBus()
        self.miners: Dict[int, SimulatedMiner] = {}
        self.reputations: Dict[int, MinerReputation] = {}
        self.validators: Dict[int, Validator] = {}
        self.tasks: List[TaskRecord] = []
        self.tasks_by_id: Dict[str, TaskRecord] = {}
        self.emission_result: Optional[EmissionResult] = None
        self.epochs: List[EpochSnapshot] = []
        self.created_at = datetime.now(timezone.utc)
        self.started_at = self.created_at
        self._task_cap = 4000
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # population
    # ------------------------------------------------------------------
    def register_miner(self, profile_key: str, name: Optional[str] = None,
                       uid: Optional[int] = None) -> SimulatedMiner:
        profile = get_profile(profile_key)
        uid = uid if uid is not None else (max(self.miners) + 1 if self.miners else 0)
        if uid in self.miners:
            raise ValueError(f"miner uid {uid} already registered")
        callsign = name or (
            f"{MINER_CALLSIGNS[uid % len(MINER_CALLSIGNS)]}-{uid:02d}")
        miner = SimulatedMiner(uid=uid, name=callsign, profile=profile,
                               seed=(self.seed or 0) + uid * 31)
        self.miners[uid] = miner
        self.reputations[uid] = MinerReputation(uid, callsign, self.config)
        self.bus.publish("miner.registered", miner_uid=uid,
                         message=f"{callsign} joined ({profile.label})",
                         data={"profile": profile.key})
        return miner

    def register_validator(self, strategy_key: str,
                           name: Optional[str] = None,
                           uid: Optional[int] = None) -> Validator:
        strategy = get_strategy(strategy_key)
        uid = uid if uid is not None else (
            max(self.validators) + 1 if self.validators else 0)
        callsign = name or f"{VALIDATOR_CALLSIGNS[uid % len(VALIDATOR_CALLSIGNS)]}-V{uid}"
        validator = Validator(uid=uid, name=callsign, strategy=strategy,
                              config=self.config, bus=self.bus,
                              seed=(self.seed or 0) + 977 * (uid + 1))
        self.validators[uid] = validator
        self.bus.publish("validator.registered", validator_uid=uid,
                         message=f"{callsign} online ({strategy.label})",
                         data={"strategy": strategy.key})
        return validator

    def populate(self, miners: int, validators: int,
                 mix: Optional[Sequence[tuple[str, float]]] = None) -> None:
        mix = list(mix or DEFAULT_MIX)
        keys = [k for k, _ in mix]
        weights = [w for _, w in mix]
        for i in range(miners):
            # deterministic round-robin over the weighted mix keeps the
            # population reproducible for a given seed
            key = self.rng.choices(keys, weights=weights, k=1)[0] if i >= len(keys) \
                else keys[i]
            self.register_miner(key)
        strategy_pool = list(STRATEGIES)
        for j in range(validators):
            self.register_validator(strategy_pool[j % len(strategy_pool)])

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------
    @property
    def network_score(self) -> float:
        reps = [r.reputation for r in self.reputations.values() if r.task_count]
        return aggregate_scores(reps) if reps else 0.5

    def step(self, validator: Optional[Validator] = None,
             difficulty_override: Optional[int] = None,
             category: Optional[Category] = None) -> TaskRecord:
        """Run exactly one task through the full pipeline."""
        if not self.miners or not self.validators:
            raise RuntimeError("network has no miners or validators")
        validator = validator or self.rng.choice(list(self.validators.values()))
        record = validator.run_task(
            miners=list(self.miners.values()), reputations=self.reputations,
            network_score=self.network_score,
            difficulty_override=difficulty_override, category=category)
        self._store(record)
        return record

    def _store(self, record: TaskRecord) -> None:
        self.tasks.append(record)
        self.tasks_by_id[record.task_id] = record
        if len(self.tasks) > self._task_cap:
            dropped = self.tasks[: len(self.tasks) - self._task_cap]
            self.tasks = self.tasks[-self._task_cap:]
            for d in dropped:
                self.tasks_by_id.pop(d.task_id, None)

    def recompute_emissions(self) -> EmissionResult:
        inputs = [EmissionInput(uid=r.uid, reputation=r.reputation,
                                task_count=r.task_count)
                  for r in self.reputations.values()]
        result = compute_emissions(inputs, self.config)
        for uid, weight in result.weights.items():
            self.reputations[uid].set_emission(weight)
        self.emission_result = result
        top = max(result.weights, key=lambda k: result.weights[k]) if result.weights else None
        self.bus.publish("emissions.updated",
                         message=f"emission weights recomputed for {len(result.eligible)} "
                                 "eligible miners",
                         data={"eligible": len(result.eligible),
                               "excluded": len(result.excluded),
                               "top_miner_uid": top})
        return result

    def close_epoch(self) -> EpochSnapshot:
        result = self.recompute_emissions()
        recent = self.tasks[-200:]
        acc = [r.accuracy for t in recent for r in t.responses if not r.rejected]
        lat = [r.execution_time_ms for t in recent for r in t.responses if not r.rejected]
        snap = EpochSnapshot(
            epoch=len(self.epochs) + 1, timestamp=datetime.now(timezone.utc),
            tasks=len(self.tasks),
            network_accuracy=round(sum(acc) / len(acc), 6) if acc else 0.0,
            network_score=self.network_score,
            mean_latency_ms=round(sum(lat) / len(lat), 1) if lat else 0.0,
            emission_gini=gini(list(result.weights.values())),
            top_miner_uid=max(result.weights, key=lambda k: result.weights[k])
            if result.weights else None)
        self.epochs.append(snap)
        self.bus.publish("epoch.closed", message=f"epoch {snap.epoch} closed",
                         data={"epoch": snap.epoch,
                               "network_accuracy": snap.network_accuracy,
                               "network_score": snap.network_score})
        return snap

    def run_simulation(self, cfg: SimulationConfig,
                       progress: Optional[Callable[[int, int], None]] = None
                       ) -> Dict[str, Any]:
        """Run a bounded simulation on THIS network instance."""
        override = cfg.difficulty_override()
        categories = [Category(c) for c in cfg.categories] if cfg.categories else None
        before = {uid: r.emission_weight for uid, r in self.reputations.items()}
        before_rank = self.leaderboard()
        start = datetime.now(timezone.utc)
        validators = list(self.validators.values())
        epoch_every = max(5, cfg.tasks // 6)
        for i in range(cfg.tasks):
            validator = validators[i % len(validators)]
            cat = self.rng.choice(categories) if categories else None
            self.step(validator=validator, difficulty_override=override, category=cat)
            if (i + 1) % epoch_every == 0:
                self.close_epoch()
            if progress:
                progress(i + 1, cfg.tasks)
        self.close_epoch()
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        after_rank = self.leaderboard()
        return {
            "config": {
                "miners": len(self.miners), "validators": len(self.validators),
                "tasks": cfg.tasks, "difficulty_mode": cfg.difficulty_mode,
                "seed": cfg.seed,
            },
            "elapsed_seconds": round(elapsed, 3),
            "tasks_completed": cfg.tasks,
            "stats": self.stats(),
            "leaderboard": after_rank,
            "rank_changes": _rank_delta(before_rank, after_rank),
            "emission_before": before,
            "emission_after": {uid: r.emission_weight
                               for uid, r in self.reputations.items()},
            "epochs": [epoch_dict(e) for e in self.epochs[-12:]],
            "adversarial": self.adversarial_summary(),
        }

    # ------------------------------------------------------------------
    # analytics
    # ------------------------------------------------------------------
    def leaderboard(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for rep in self.reputations.values():
            if category and category not in rep.category:
                continue
            snap = rep.snapshot()
            snap["profile"] = self.miners[rep.uid].profile.key
            snap["profile_label"] = self.miners[rep.uid].profile.label
            if category:
                cs = rep.category[category]
                snap["category_accuracy"] = cs.accuracy
                snap["category_score"] = cs.mean_score
                snap["category_tasks"] = cs.tasks
                snap["sort_key"] = cs.mean_score
            else:
                snap["sort_key"] = rep.reputation
            rows.append(snap)
        rows.sort(key=lambda r: (r["sort_key"], r["task_count"]), reverse=True)
        for i, row in enumerate(rows, start=1):
            row["rank"] = i
        return rows

    def stats(self) -> Dict[str, Any]:
        responses = [r for t in self.tasks for r in t.responses if not r.rejected]
        accs = [r.accuracy for r in responses]
        lats = [r.execution_time_ms for r in responses]
        scores = [r.score for r in responses]
        probes = [r.probe for t in self.tasks for r in t.responses if r.probe]
        rejected = sum(1 for t in self.tasks for r in t.responses if r.rejected)
        window = datetime.now(timezone.utc) - timedelta(minutes=5)
        recent_tasks = [t for t in self.tasks if t.created_at >= window]
        uptime = max(1e-6, (datetime.now(timezone.utc) - self.started_at).total_seconds())
        # throughput measured over the span of the most recent 100 tasks; the
        # local simulation runs far faster than a real subnet epoch, which is
        # why this is reported as *simulated* throughput in the UI.
        span_tasks = self.tasks[-100:]
        span = ((span_tasks[-1].created_at - span_tasks[0].created_at).total_seconds()
                if len(span_tasks) > 1 else 0.0)
        return {
            "mode": self.mode,
            "netuid": self.netuid,
            "active_miners": len(self.miners),
            "active_validators": len(self.validators),
            "tasks_verified": len(self.tasks),
            "responses_evaluated": len(responses),
            "network_accuracy": round(sum(accs) / len(accs), 6) if accs else 0.0,
            "network_score": self.network_score,
            "mean_latency_ms": round(sum(lats) / len(lats), 1) if lats else 0.0,
            "p95_latency_ms": round(_percentile(lats, 0.95), 1) if lats else 0.0,
            "mean_task_score": round(sum(scores) / len(scores), 6) if scores else 0.0,
            "throughput_per_min": round(len(span_tasks) / (span / 60.0), 2)
            if span > 0.5 else round(len(self.tasks) / (uptime / 60.0), 2),
            "throughput_is_simulated": self.mode == "simulation",
            "recent_throughput_per_min": round(len(recent_tasks) / 5.0, 2),
            "robustness_probes": len(probes),
            "robustness_hold_rate": round(
                sum(1 for p in probes if p.get("consistent")) / len(probes), 6)
            if probes else 0.0,
            "rejected_responses": rejected,
            "flagged_miners": sum(1 for r in self.reputations.values() if r.flags),
            "emission_eligible": len(self.emission_result.eligible)
            if self.emission_result else 0,
            "emission_gini": gini([r.emission_weight
                                   for r in self.reputations.values()]),
            "epochs": len(self.epochs),
            "events": len(self.bus),
            "uptime_seconds": round(uptime, 1),
        }

    def health(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        validators = []
        # A validator is judged against network activity, not wall clock: an idle
        # subnet has idle validators, which is not a fault. It is "stale" only if
        # other validators have been scoring tasks while it has not.
        # "Stale" must mean *fell behind while the network was working*, not
        # merely "idle". Wall-clock idleness produces false alarms whenever an
        # operator triggers a handful of tasks by hand, because whichever
        # validators were not chosen look stale. Instead, count how many tasks
        # the network completed after this validator last acted, and allow a
        # generous share before calling it behind.
        backlog_allowance = max(10, 3 * max(1, len(self.validators)))
        for v in self.validators.values():
            idle = (now - v.last_active).total_seconds() if v.last_active else None
            missed = sum(1 for t in self.tasks
                         if v.last_active is not None and t.created_at > v.last_active)
            behind = missed > backlog_allowance
            never_ran = v.last_active is None and bool(self.tasks)
            validators.append({
                "uid": v.uid, "name": v.name,
                "status": "stale" if (behind or never_ran) else "healthy",
                "tasks_scored": v.tasks_scored, "rejections": v.rejections,
                "idle_seconds": round(idle, 1) if idle is not None else None,
                "tasks_missed": missed,
            })
        unhealthy = [r.uid for r in self.reputations.values()
                     if r.task_count >= 5 and r.reputation < self.config.emission.floor_score]
        stats = self.stats()
        queue_depth = sum(1 for t in self.tasks if t.status.value not in
                          ("scored", "verified", "failed", "expired"))
        return {
            "subnet_status": "operational" if self.validators and self.miners else "degraded",
            "mode": self.mode,
            "validators": validators,
            "miner_health": {
                "total": len(self.miners),
                "healthy": len(self.miners) - len(unhealthy),
                "underperforming": len(unhealthy),
                "flagged": stats["flagged_miners"],
            },
            "task_queue_depth": queue_depth,
            "verification_latency_ms": stats["mean_latency_ms"],
            "p95_latency_ms": stats["p95_latency_ms"],
            "last_epoch": self.epochs[-1].epoch if self.epochs else 0,
        }

    def adversarial_summary(self) -> Dict[str, Any]:
        probes = [(t, r) for t in self.tasks for r in t.responses if r.probe]
        held = sum(1 for _, r in probes if r.probe and r.probe.get("consistent"))
        by_miner: Dict[int, Dict[str, int]] = {}
        for _, r in probes:
            entry = by_miner.setdefault(r.miner_uid, {"probes": 0, "held": 0})
            entry["probes"] += 1
            entry["held"] += 1 if r.probe.get("consistent") else 0
        return {
            "probes": len(probes),
            "held": held,
            "flipped": len(probes) - held,
            "hold_rate": round(held / len(probes), 6) if probes else 0.0,
            "by_miner": by_miner,
        }

    def category_breakdown(self) -> List[Dict[str, Any]]:
        out = []
        for cat in Category:
            tasks = [t for t in self.tasks if t.category == cat]
            responses = [r for t in tasks for r in t.responses if not r.rejected]
            accs = [r.accuracy for r in responses]
            out.append({
                "category": cat.value,
                "tasks": len(tasks),
                "responses": len(responses),
                "accuracy": round(sum(accs) / len(accs), 6) if accs else 0.0,
                "mean_difficulty": round(
                    sum(t.difficulty for t in tasks) / len(tasks), 2) if tasks else 0.0,
            })
        return out


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def epoch_dict(e: EpochSnapshot) -> Dict[str, Any]:
    return {
        "epoch": e.epoch, "timestamp": e.timestamp.isoformat(), "tasks": e.tasks,
        "network_accuracy": e.network_accuracy, "network_score": e.network_score,
        "mean_latency_ms": e.mean_latency_ms, "emission_gini": e.emission_gini,
        "top_miner_uid": e.top_miner_uid,
    }


def gini(values: Sequence[float]) -> float:
    """Inequality of the emission distribution (0 = equal, ->1 = concentrated)."""
    vals = sorted(max(0.0, v) for v in values if v is not None and math.isfinite(v))
    n = len(vals)
    total = sum(vals)
    if n == 0 or total <= 0:
        return 0.0
    cum = sum((i + 1) * v for i, v in enumerate(vals))
    return round((2 * cum) / (n * total) - (n + 1) / n, 6)


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return float(ordered[idx])


def _rank_delta(before: List[Dict[str, Any]], after: List[Dict[str, Any]]
                ) -> List[Dict[str, Any]]:
    prev = {row["uid"]: row["rank"] for row in before}
    out = []
    for row in after:
        old = prev.get(row["uid"])
        out.append({
            "uid": row["uid"], "name": row["name"], "rank": row["rank"],
            "previous_rank": old,
            "delta": (old - row["rank"]) if old is not None else 0,
            "reputation": row["reputation"],
            "emission_weight": row["emission_weight"],
        })
    return out
