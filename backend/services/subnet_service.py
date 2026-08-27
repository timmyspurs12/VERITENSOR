"""Application service: owns the subnet runtime and mediates all access.

Responsibilities
----------------
* build/seed the runtime on startup (real pipeline execution, not fixtures)
* expose read models for the API (already sanitised: no ground truth)
* run bounded simulations and the hackathon demo under an async lock
* mirror state into the database through the repository
* choose the adapter (SimulationAdapter vs BittensorAdapter) and report which
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.config import Settings, get_settings
from ..core.logging import log_event
from ..models.base import session_scope
from ..repositories.subnet_repository import SubnetRepository
from subnet.adapters import (AdapterMode, BittensorAdapter, SimulationAdapter,
                             build_adapter, bittensor_available)
from subnet.chain.sdk import probe as probe_sdk
from subnet.protocol.messages import Category
from subnet.scoring.config import DEFAULT_CONFIG
from subnet.scoring.engine import ScoringEngine
from subnet.simulation.network import (SimulationConfig, SubnetNetwork,
                                       epoch_dict)
from subnet.simulation.seed import seed_network
from subnet.validator.records import TaskRecord

log = logging.getLogger("veritensor.service")


class SubnetService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.config = DEFAULT_CONFIG
        self.scorer = ScoringEngine(self.config)
        self.network: SubnetNetwork = SubnetNetwork(
            config=self.config, seed=self.settings.random_seed,
            mode="simulation", netuid=self.settings.simulation_netuid)
        self.adapter = build_adapter(self.network, self.settings.simulation_mode)
        self._lock = asyncio.Lock()
        self._sim_running = False
        self._last_persist_seq = 0
        self.ready = False
        self.boot_report: Dict[str, Any] = {}
        self._chain_status_cache: Optional[tuple[float, Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def bootstrap(self) -> None:
        """Seed the network by executing real verification rounds."""
        started = time.perf_counter()
        s = self.settings
        if s.autoseed:
            self.network = seed_network(miners=s.seed_miners,
                                        validators=s.seed_validators,
                                        tasks=s.seed_tasks, seed=s.random_seed,
                                        config=self.config)
            self.network.netuid = s.simulation_netuid
        else:
            self.network.populate(miners=s.seed_miners, validators=s.seed_validators)
        self.adapter = build_adapter(self.network, s.simulation_mode)
        self.persist()
        self.ready = True
        self.boot_report = {
            "seeded": s.autoseed,
            "miners": len(self.network.miners),
            "validators": len(self.network.validators),
            "tasks": len(self.network.tasks),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "adapter": self.adapter.mode.value,
            "on_chain": self.adapter.get_network_state().on_chain,
        }
        log_event(log, "subnet bootstrapped", **self.boot_report)

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def persist(self) -> None:
        try:
            with session_scope() as session:
                repo = SubnetRepository(session)
                for uid, rep in self.network.reputations.items():
                    repo.upsert_miner(rep.snapshot(),
                                      self.network.miners[uid].profile.key)
                for v in self.network.validators.values():
                    repo.upsert_validator(v.snapshot())
                for record in self.network.tasks[-500:]:
                    repo.save_task(record)
                for snap in self.network.epochs:
                    pass  # epochs are appended below only when new
                new_events = self.network.bus.recent(limit=2000,
                                                     after_seq=self._last_persist_seq)
                if new_events:
                    repo.save_events(new_events)
                    self._last_persist_seq = new_events[-1].seq
        except Exception as exc:  # persistence must never break the API
            log.warning("persistence skipped: %s", exc)

    # ------------------------------------------------------------------
    # read models
    # ------------------------------------------------------------------
    def mode_info(self) -> Dict[str, Any]:
        """Unambiguous statement of where the served numbers came from.

        Three mutually exclusive modes, never blended:

        ``LOCAL_SIMULATION``  in-process engine, no wallets, no chain
        ``LOCAL_NEURONS``     separate neuron processes, real wallets, no chain
        ``BITTENSOR_TESTNET`` neurons registered on chain, weights submitted
        """
        state = self.adapter.get_network_state()
        caps = probe_sdk()
        if state.mode == AdapterMode.SIMULATION:
            mode = "LOCAL_SIMULATION"
        elif state.mode == AdapterMode.BITTENSOR_MAINNET:
            mode = "BITTENSOR_MAINNET"
        else:
            mode = "BITTENSOR_TESTNET"
        return {
            "mode": mode,
            "adapter": state.mode.value,
            "on_chain": state.on_chain,
            "connected": state.connected,
            "netuid": state.netuid,
            "chain_endpoint": state.chain_endpoint,
            "block": state.block,
            "wallet_configured": bool(state.wallet and state.hotkey),
            "bittensor_sdk_installed": caps.installed,
            "bittensor_sdk_version": caps.version,
            "bittensor_sdk_generation": caps.generation,
            "signed_transport_available": caps.usable_for_transport,
            "synthetic_data": state.mode == AdapterMode.SIMULATION,
            "notes": state.notes,
        }

    def chain_status(self, max_age_s: float = 30.0) -> Dict[str, Any]:
        """Read-only chain probe for the dashboard.

        Never signs or submits. Reports exactly which testnet prerequisites are
        satisfied so the UI can show real blockers instead of a green light.

        Cached for ``max_age_s``: a chain round trip costs seconds, and the
        dashboard polls. The cached payload carries ``probed_at`` so a stale
        reading is never mistaken for a live one.
        """
        now = time.time()
        cached = self._chain_status_cache
        if cached and now - cached[0] < max_age_s:
            payload = dict(cached[1])
            payload["cached"] = True
            payload["age_seconds"] = round(now - cached[0], 1)
            return payload
        payload = self._probe_chain()
        payload["probed_at"] = datetime.now(timezone.utc).isoformat()
        payload["cached"] = False
        payload["age_seconds"] = 0.0
        self._chain_status_cache = (now, payload)
        return payload

    def _probe_chain(self) -> Dict[str, Any]:
        caps = probe_sdk()
        settings = self.settings
        payload: Dict[str, Any] = {
            "sdk": caps.as_dict(),
            "simulation_mode": settings.simulation_mode,
            "configured": {
                "netuid": settings.subnet_netuid,
                "network": settings.bittensor_network,
                "wallet": bool(settings.bittensor_wallet_name),
                "hotkey": bool(settings.bittensor_hotkey_name),
            },
            "mode_info": self.mode_info(),
        }
        if not caps.usable_for_chain:
            payload["reachable"] = False
            payload["reason"] = ("bittensor SDK with chain support is not "
                                 "installed") if not caps.installed else                 "installed SDK lacks the required chain API"
            return payload
        try:
            adapter = BittensorAdapter(
                netuid=settings.subnet_netuid,
                network=settings.bittensor_network,
                wallet_name=settings.bittensor_wallet_name or None,
                hotkey_name=settings.bittensor_hotkey_name or None)
            report = adapter.preflight()
            payload["preflight"] = report
            payload["reachable"] = bool(report["checks"].get("chain_reachable"))
            payload["ready_to_submit_weights"] = bool(
                report.get("ready_to_submit_weights"))
            # Surface the concrete failure rather than an unexplained red light:
            # the panel is useless if it says "unreachable" with no reason.
            if not payload["reachable"]:
                payload["reason"] = report.get(
                    "chain_error", "chain endpoint did not respond")
        except Exception as exc:
            payload["reachable"] = False
            payload["reason"] = f"{type(exc).__name__}: {exc}"
        return payload

    def stats(self) -> Dict[str, Any]:
        data = self.network.stats()
        data["mode_info"] = self.mode_info()
        data["categories"] = self.network.category_breakdown()
        data["config"] = {"weights": self.config.weights.as_dict(),
                          "emission": {
                              "temperature": self.config.emission.temperature,
                              "floor_score": self.config.emission.floor_score,
                              "max_share": self.config.emission.max_share,
                              "min_tasks": self.config.emission.min_tasks}}
        return data

    def epochs(self, limit: int = 40) -> List[Dict[str, Any]]:
        return [epoch_dict(e) for e in self.network.epochs[-limit:]]

    def leaderboard(self, category: Optional[str] = None, limit: int = 100,
                    offset: int = 0) -> Dict[str, Any]:
        rows = self.network.leaderboard(category)
        return {"total": len(rows), "items": rows[offset: offset + limit]}

    def miner_detail(self, uid: int) -> Optional[Dict[str, Any]]:
        rep = self.network.reputations.get(uid)
        if rep is None:
            return None
        miner = self.network.miners[uid]
        history = [{"timestamp": h.timestamp.isoformat(), "task_id": h.task_id,
                    "score": h.score, "rolling_score": h.rolling_score,
                    "accuracy": h.accuracy, "emission_weight": h.emission_weight}
                   for h in list(rep.history)[-200:]]
        recent = []
        failures: Dict[str, int] = {}
        for task in reversed(self.network.tasks):
            for r in task.responses:
                if r.miner_uid != uid:
                    continue
                if len(recent) < 25:
                    recent.append({
                        "task_id": task.task_id, "category": task.category.value,
                        "difficulty": task.difficulty, "correct": r.correct,
                        "score": r.score, "confidence": r.confidence,
                        "latency_ms": r.execution_time_ms,
                        "breakdown": r.breakdown, "flags": r.flags,
                        "probe": r.probe,
                        "created_at": task.created_at.isoformat()})
                if not r.correct and not r.rejected:
                    failures[task.category.value] = failures.get(task.category.value, 0) + 1
            if len(recent) >= 25:
                break
        snapshot = rep.snapshot()
        snapshot.update({
            "profile": miner.profile.key,
            "profile_label": miner.profile.label,
            "profile_description": miner.profile.description,
            "backend": miner.backend_name,
            "synthetic": True,
            "history": history,
            "emission_history": list(rep.emission_history)[-200:],
            "recent_tasks": recent,
            "failure_analysis": failures,
            "probe_outcomes": rep.probe_outcomes[-50:],
            "specialisation": max(snapshot["categories"].items(),
                                  key=lambda kv: kv[1]["mean_score"])[0]
            if snapshot["categories"] else None,
        })
        return snapshot

    def score_explanation(self, uid: int, task_id: Optional[str] = None
                          ) -> Optional[Dict[str, Any]]:
        """Score Explorer payload: exact arithmetic behind a miner's score."""
        rep = self.network.reputations.get(uid)
        if rep is None:
            return None
        target = None
        if task_id:
            record = self.network.tasks_by_id.get(task_id)
            if record:
                target = next((r for r in record.responses if r.miner_uid == uid), None)
        else:
            for record in reversed(self.network.tasks):
                target = next((r for r in record.responses
                               if r.miner_uid == uid and not r.rejected), None)
                if target:
                    task_id = record.task_id
                    break
        if target is None:
            return None
        weights = self.config.weights.as_dict()
        rows = [{"component": k, "value": round(v, 6),
                 "weight": weights.get(k, 0.0),
                 "contribution": round(v * weights.get(k, 0.0), 6)}
                for k, v in target.breakdown.items()]
        subtotal = round(sum(r["contribution"] for r in rows), 6)
        penalty = round(min(self.config.penalties.cap,
                            sum(target.penalties.values())), 6)
        return {
            "miner_uid": uid, "miner_name": rep.name, "task_id": task_id,
            "rows": rows, "subtotal": subtotal, "penalties": target.penalties,
            "penalty_total": penalty, "final_score": target.score,
            "formula": ("final = Σ(component × weight) × (1 − penalties)"),
            "reputation_after": rep.reputation,
            "ema_alpha": self.config.reputation.ema_alpha,
            "emission_weight": rep.emission_weight,
        }

    def validators(self) -> List[Dict[str, Any]]:
        return [v.snapshot() | {"synthetic": True}
                for v in self.network.validators.values()]

    def tasks(self, limit: int = 25, offset: int = 0, category: Optional[str] = None,
              status: Optional[str] = None, validator_uid: Optional[int] = None,
              min_difficulty: Optional[int] = None,
              max_difficulty: Optional[int] = None) -> Dict[str, Any]:
        items = list(reversed(self.network.tasks))
        if category:
            items = [t for t in items if t.category.value == category]
        if status:
            items = [t for t in items if t.status.value == status]
        if validator_uid is not None:
            items = [t for t in items if t.validator_uid == validator_uid]
        if min_difficulty is not None:
            items = [t for t in items if t.difficulty >= min_difficulty]
        if max_difficulty is not None:
            items = [t for t in items if t.difficulty <= max_difficulty]
        total = len(items)
        page = items[offset: offset + limit]
        return {"total": total, "limit": limit, "offset": offset,
                "items": [self._task_summary(t) for t in page]}

    @staticmethod
    def _task_summary(t: TaskRecord) -> Dict[str, Any]:
        return {
            "task_id": t.task_id, "category": t.category.value,
            "difficulty": t.difficulty, "kind": t.kind,
            "verification_type": t.verification_type.value,
            "status": t.status.value, "validator_uid": t.validator_uid,
            "validator_name": t.validator_name, "generator": t.generator,
            "created_at": t.created_at.isoformat(),
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "duration_ms": t.duration_ms,
            "responses": len(t.responses),
            "correct_responses": sum(1 for r in t.responses if r.correct),
            "consensus": t.consensus,
            "prompt_excerpt": t.prompt[:180],
            "synthetic": True,
        }

    def task_detail(self, task_id: str, reveal: bool = False) -> Optional[Dict[str, Any]]:
        record = self.network.tasks_by_id.get(task_id)
        if record is None:
            return None
        return record.public_dict(reveal_truth=reveal) | {"synthetic": True}

    def emissions(self) -> Dict[str, Any]:
        result = self.network.emission_result
        rows = []
        for rep in self.network.reputations.values():
            rows.append({
                "uid": rep.uid, "name": rep.name,
                "reputation": rep.reputation, "task_count": rep.task_count,
                "emission_weight": rep.emission_weight,
                "history": list(rep.emission_history)[-60:],
                "eligible": result is not None and rep.uid in result.eligible,
                "exclusion_reason": (result.excluded.get(rep.uid)
                                     if result else None),
            })
        rows.sort(key=lambda r: r["emission_weight"], reverse=True)
        return {
            "total_weight": round(sum(r["emission_weight"] for r in rows), 9),
            "gini": self.network.stats()["emission_gini"],
            "eligible": len(result.eligible) if result else 0,
            "excluded": result.excluded if result else {},
            "policy": {
                "temperature": self.config.emission.temperature,
                "floor_score": self.config.emission.floor_score,
                "max_share": self.config.emission.max_share,
                "min_tasks": self.config.emission.min_tasks,
            },
            "items": rows,
            "epochs": self.epochs(30),
        }

    def events(self, limit: int = 100, after_seq: int = 0,
               kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.network.bus.recent(limit, after_seq, kinds)]

    def mechanism_config(self) -> Dict[str, Any]:
        return self.config.as_dict()

    # ------------------------------------------------------------------
    # write paths
    # ------------------------------------------------------------------
    async def run_task(self, category: Optional[str] = None,
                       difficulty: Optional[int] = None,
                       validator_uid: Optional[int] = None) -> Dict[str, Any]:
        async with self._lock:
            validator = self.network.validators.get(validator_uid) \
                if validator_uid is not None else None
            record = await asyncio.to_thread(
                self.network.step, validator,
                difficulty, Category(category) if category else None)
            self.network.recompute_emissions()
            self.persist()
        log_event(log, "task executed", task_id=record.task_id,
                  category=record.category.value, difficulty=record.difficulty,
                  responses=len(record.responses))
        return self.task_detail(record.task_id) or {}

    async def run_simulation(self, miners: int, validators: int, tasks: int,
                             difficulty_mode: str, seed: Optional[int] = None,
                             fresh_network: bool = True) -> Dict[str, Any]:
        """Bounded simulation. Runs off the event loop so the API stays live."""
        s = self.settings
        tasks = max(1, min(tasks, s.max_simulation_tasks))
        miners = max(1, min(miners, s.max_simulation_miners))
        validators = max(1, min(validators, 7))
        async with self._lock:
            if self._sim_running:
                raise RuntimeError("a simulation is already running")
            self._sim_running = True
        try:
            def _run() -> Dict[str, Any]:
                if fresh_network:
                    net = SubnetNetwork(config=self.config, seed=seed,
                                        mode="simulation",
                                        netuid=s.simulation_netuid)
                    net.populate(miners=miners, validators=validators)
                else:
                    net = self.network
                result = net.run_simulation(SimulationConfig(
                    miners=miners, validators=validators, tasks=tasks,
                    difficulty_mode=difficulty_mode, seed=seed))
                result["events"] = [e.to_dict() for e in net.bus.recent(400)]
                result["health"] = net.health()
                result["categories"] = net.category_breakdown()
                result["mode_info"] = self.mode_info()
                result["network_id"] = id(net)
                return result

            started = time.perf_counter()
            result = await asyncio.to_thread(_run)
            result["wall_clock_seconds"] = round(time.perf_counter() - started, 3)
            log_event(log, "simulation completed", miners=miners,
                      validators=validators, tasks=tasks,
                      seconds=result["wall_clock_seconds"])
            return result
        finally:
            self._sim_running = False

    async def run_demo(self) -> Dict[str, Any]:
        """Hackathon demo: one task, end to end, with every stage captured."""
        async with self._lock:
            before = {r["uid"]: r["rank"] for r in self.network.leaderboard()}
            before_emissions = {uid: r.emission_weight
                                for uid, r in self.network.reputations.items()}
            start_seq = self.network.bus.recent(1)[-1].seq if len(self.network.bus) else 0

            def _run() -> Dict[str, Any]:
                record = self.network.step()
                emissions = self.network.recompute_emissions()
                return {"record": record, "emissions": emissions}

            out = await asyncio.to_thread(_run)
            record: TaskRecord = out["record"]
            after = self.network.leaderboard()
            after_rank = {r["uid"]: r["rank"] for r in after}
            self.persist()

        stages = [
            {"stage": "generate", "label": "Task generated",
             "detail": f"{record.category.value} · difficulty {record.difficulty} · "
                       f"{record.generator}"},
            {"stage": "dispatch", "label": "Dispatched to miners",
             "detail": f"{len(record.responses) + len(record.dropped_miners)} miners queried"},
            {"stage": "responses", "label": "Responses received",
             "detail": f"{len(record.responses)} responses, "
                       f"{len(record.dropped_miners)} timeouts"},
            {"stage": "verify", "label": "Independently verified",
             "detail": f"{sum(1 for r in record.responses if r.correct)} correct"},
            {"stage": "robustness", "label": "Adversarial mutation probes",
             "detail": f"{sum(1 for r in record.responses if r.probe)} probes issued"},
            {"stage": "score", "label": "Multidimensional scoring",
             "detail": "accuracy / evidence / robustness / calibration / latency"},
            {"stage": "reputation", "label": "Reputation updated",
             "detail": f"EMA α={self.config.reputation.ema_alpha}"},
            {"stage": "emissions", "label": "Emission weights recomputed",
             "detail": f"{len(out['emissions'].eligible)} eligible miners"},
        ]
        movements = [{"uid": uid, "name": self.network.reputations[uid].name,
                      "previous_rank": before.get(uid), "rank": rank,
                      "delta": (before.get(uid, rank) - rank),
                      "emission_before": round(before_emissions.get(uid, 0.0), 6),
                      "emission_after": round(
                          self.network.reputations[uid].emission_weight, 6)}
                     for uid, rank in after_rank.items()]
        movements.sort(key=lambda m: m["rank"])
        return {
            "task": self.task_detail(record.task_id, reveal=True),
            "stages": stages,
            "leaderboard": after[:12],
            "movements": movements[:12],
            "events": [e.to_dict()
                       for e in self.network.bus.recent(200, after_seq=start_seq)],
            "stats": self.stats(),
            "mode_info": self.mode_info(),
        }

    def register_miner(self, profile: str, name: Optional[str]) -> Dict[str, Any]:
        miner = self.network.register_miner(profile_key=profile, name=name)
        self.persist()
        return {"uid": miner.uid, "name": miner.name,
                "profile": miner.profile.key, "synthetic": True}

    def reset(self) -> Dict[str, Any]:
        self.network = SubnetNetwork(config=self.config,
                                     seed=self.settings.random_seed,
                                     mode="simulation",
                                     netuid=self.settings.simulation_netuid)
        self.network.populate(self.settings.seed_miners, self.settings.seed_validators)
        self.adapter = build_adapter(self.network, self.settings.simulation_mode)
        self._last_persist_seq = 0
        return {"reset": True, "miners": len(self.network.miners),
                "validators": len(self.network.validators)}


_service: Optional[SubnetService] = None


def get_service() -> SubnetService:
    global _service
    if _service is None:
        _service = SubnetService()
    return _service


def set_service(service: SubnetService) -> None:
    global _service
    _service = service
