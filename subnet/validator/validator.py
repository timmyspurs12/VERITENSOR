"""Validator: orchestrates the verification pipeline for one round."""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from ..miner.simulated import SimulatedMiner
from ..protocol.messages import Category, TaskStatus
from ..protocol.signing import task_commitment
from ..scoring.antigaming import AntiGamingGuard, RateLimitRule
from ..scoring.config import DEFAULT_CONFIG, MechanismConfig
from ..scoring.engine import ScoringEngine
from ..scoring.reputation import MinerReputation
from ..tasks.engine import TaskEngine
from . import pipeline as P
from .events import EventBus
from .records import ResponseRecord, TaskRecord
from .strategies import STRATEGIES, ValidatorStrategy


class Validator:
    """One validator instance.

    Owns its own task engine RNG, anti-gaming guard and scoring engine so that
    multiple validators in a simulation are genuinely independent evaluators
    rather than shared state with different labels.
    """

    def __init__(self, uid: int, name: str, strategy: ValidatorStrategy,
                 config: MechanismConfig = DEFAULT_CONFIG,
                 bus: Optional[EventBus] = None, seed: Optional[int] = None) -> None:
        self.uid = uid
        self.name = name
        self.strategy = strategy
        self.config = config
        self.bus = bus or EventBus()
        self.rng = random.Random(seed if seed is not None else uid * 104729)
        self.engine = TaskEngine(seed=seed)
        self.scorer = ScoringEngine(config)
        # NOTE: the local simulation compresses hours of subnet traffic into
        # milliseconds, so the per-miner request budget is widened here. The
        # *transport* rate limit that protects the real API lives in
        # backend/core/security.py::RateLimitMiddleware and is exercised by
        # tests/test_anti_gaming.py::test_rate_limiter_blocks_burst.
        self.guard = AntiGamingGuard(
            config, RateLimitRule(max_requests=100_000, per_seconds=60))
        self.tasks_issued = 0
        self.tasks_scored = 0
        self.probes_issued = 0
        self.rejections = 0
        self.last_active: Optional[datetime] = None
        self._commit_secret = os.getenv("VERITENSOR_COMMIT_SECRET", "local-dev-secret")

    # -- helpers -----------------------------------------------------------
    def choose_difficulty(self, network_score: float,
                          override: Optional[int] = None) -> int:
        if override is not None:
            return max(1, min(10, int(override)))
        if self.strategy.adaptivity <= 0:
            return self.strategy.fixed_difficulty
        return P.next_difficulty(network_score, self.config, self.rng)

    # -- main round --------------------------------------------------------
    def run_task(self, miners: Sequence[SimulatedMiner],
                 reputations: Dict[int, MinerReputation],
                 network_score: float = 0.5,
                 difficulty_override: Optional[int] = None,
                 category: Optional[Category] = None) -> TaskRecord:
        """Execute the full pipeline for a single task and return its record."""
        started = datetime.now(timezone.utc)
        cat = category or self.strategy.pick_category(self.rng)
        difficulty = self.choose_difficulty(network_score, difficulty_override)

        # 1. generate ------------------------------------------------------
        # Benchmark rotation: the miner cannot tell whether this item is freshly
        # generated, drawn from the private held-out bank, or an adversarial
        # mutation of a task it has effectively already seen.
        kind = self.engine.draw_kind()
        task = None
        if kind == "hidden_benchmark":
            task = self.engine.generate_benchmark(cat, difficulty)
            if task is not None:
                task.request.validator_uid = self.uid
                self.guard.register_task(task.request)
        if task is None:
            task = P.generate(self.engine, cat, difficulty, self.guard, self.uid)
            if kind == "hidden_benchmark":
                kind = "generated"          # bank empty for this family
        if kind in ("adversarial", "mutation"):
            variant = self.engine.mutate(task)
            if variant is not None:
                variant.request.validator_uid = self.uid
                self.guard.register_task(variant.request)
                task = variant
            else:
                kind = "generated"
        self.tasks_issued += 1
        difficulty = task.request.difficulty
        commitment = task_commitment(task.request.task_id, task.request.nonce,
                                     task.ground_truth.answer, self._commit_secret)
        record = TaskRecord(
            task_id=task.request.task_id, category=cat, difficulty=difficulty,
            parent_task_id=task.request.parent_task_id,
            prompt=task.request.prompt,
            verification_type=task.request.verification_type,
            validator_uid=self.uid, validator_name=self.name,
            generator=task.generator, status=TaskStatus.GENERATED,
            created_at=started, kind=kind, commitment=commitment)
        self.bus.publish("task.generated", task_id=record.task_id,
                         validator_uid=self.uid,
                         message=f"{cat.value} task generated (d{difficulty})",
                         data={"category": cat.value, "difficulty": difficulty,
                               "kind": kind, "generator": task.generator,
                               "verification_type": record.verification_type.value})

        # 2. dispatch ------------------------------------------------------
        selected = self.strategy.sample_miners(miners, self.rng)
        record.status = TaskStatus.DISPATCHED
        self.bus.publish("task.dispatched", task_id=record.task_id,
                         validator_uid=self.uid,
                         message=f"dispatched to {len(selected)} miners",
                         data={"miner_uids": [m.uid for m in selected]})

        dispatched = P.dispatch(task, selected)
        record.dropped_miners = dispatched.dropped
        record.status = TaskStatus.RESPONSES_RECEIVED
        for uid in dispatched.dropped:
            self.bus.publish("miner.dropped", task_id=record.task_id, miner_uid=uid,
                             level="warning", message="no response before deadline")

        # 3. validate + score ---------------------------------------------
        breakdowns = {}
        for response in dispatched.responses:
            miner = next(m for m in selected if m.uid == response.miner_uid)
            rep = reputations.get(response.miner_uid)
            guard_report = P.validate_response(response, task.request, self.guard)
            if guard_report.rejected:
                self.rejections += 1
                record.responses.append(ResponseRecord(
                    miner_uid=response.miner_uid, miner_name=miner.name,
                    answer="", confidence=response.confidence,
                    execution_time_ms=response.execution_time_ms, evidence=[],
                    correct=False, accuracy=0.0, score=0.0, breakdown={},
                    penalties=dict(guard_report.penalties),
                    flags=list(guard_report.flags), rejected=True,
                    rejection_reason=guard_report.reason))
                self.bus.publish("response.rejected", task_id=record.task_id,
                                 miner_uid=response.miner_uid, level="warning",
                                 message=f"rejected: {guard_report.reason}")
                continue

            ctx = P.build_context(rep, guard_report, self.config)
            breakdown = P.score_response(self.scorer, response, task.ground_truth, ctx)
            breakdowns[response.miner_uid] = breakdown
            self.bus.publish("miner.responded", task_id=record.task_id,
                             miner_uid=response.miner_uid,
                             message=f"answered in {response.execution_time_ms} ms",
                             data={"confidence": response.confidence,
                                   "latency_ms": response.execution_time_ms,
                                   "correct": breakdown.accuracy >= 1.0})

            # 4. robustness probe -----------------------------------------
            probe_outcome: Optional[bool] = None
            probe_data = None
            if (breakdown.accuracy >= 1.0
                    and self.rng.random() < self.strategy.probe_rate):
                probe = P.robustness_probe(self.engine, task, miner, self.guard,
                                           self.scorer)
                if probe is not None:
                    consistent, mutated, probe_response = probe
                    probe_outcome = consistent
                    self.probes_issued += 1
                    probe_data = {
                        "mutation_task_id": mutated.request.task_id,
                        "consistent": consistent,
                        "answer": probe_response.answer if probe_response else None,
                        "prompt_excerpt": mutated.request.prompt[:400],
                    }
                    self.bus.publish(
                        "robustness.probe", task_id=record.task_id,
                        miner_uid=response.miner_uid,
                        level="info" if consistent else "warning",
                        message="mutation probe " + ("held" if consistent else "flipped"),
                        data=probe_data)

            # 5. reputation update ----------------------------------------
            if rep is not None:
                P.update_reputation(rep, task, response, breakdown, probe_outcome,
                                    guard_report.flags)
                if probe_outcome is not None:
                    # recompute robustness now that the probe is recorded
                    from ..scoring.components import robustness_score
                    rep.last_components["robustness"] = robustness_score(
                        rep.probe_outcomes, self.config.robustness)

            record.responses.append(ResponseRecord(
                miner_uid=response.miner_uid, miner_name=miner.name,
                answer=response.answer, confidence=response.confidence,
                execution_time_ms=response.execution_time_ms,
                evidence=[e.content for e in response.evidence],
                correct=breakdown.accuracy >= 1.0, accuracy=breakdown.accuracy,
                score=breakdown.final_score,
                breakdown={"accuracy": breakdown.accuracy,
                           "evidence": breakdown.evidence,
                           "robustness": breakdown.robustness,
                           "calibration": breakdown.calibration,
                           "latency": breakdown.latency},
                penalties=dict(breakdown.penalties),
                flags=list(guard_report.flags), probe=probe_data,
                model_metadata=dict(response.model_metadata)))

        # 6. consensus + close --------------------------------------------
        scored_responses = [r for r in dispatched.responses
                            if r.miner_uid in breakdowns]
        record.consensus = P.consensus(scored_responses, breakdowns, reputations)
        record.status = TaskStatus.SCORED
        record.completed_at = datetime.now(timezone.utc)
        record.ground_truth = task.ground_truth.answer
        record.ground_truth_explanation = task.ground_truth.explanation
        self.tasks_scored += 1
        self.last_active = record.completed_at
        self.bus.publish("task.verified", task_id=record.task_id,
                         validator_uid=self.uid,
                         message=("verified with "
                                  f"{record.consensus['verification_confidence']:.2f} "
                                  "confidence"),
                         data={"consensus": record.consensus,
                               "scored": len(scored_responses)})
        return record

    def snapshot(self) -> Dict[str, object]:
        return {
            "uid": self.uid,
            "name": self.name,
            "strategy": self.strategy.key,
            "strategy_label": self.strategy.label,
            "description": self.strategy.description,
            "tasks_issued": self.tasks_issued,
            "tasks_scored": self.tasks_scored,
            "probes_issued": self.probes_issued,
            "rejections": self.rejections,
            "sample_fraction": self.strategy.sample_fraction,
            "probe_rate": self.strategy.probe_rate,
            "adaptive": self.strategy.adaptivity > 0,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "guard": self.guard.stats(),
        }
