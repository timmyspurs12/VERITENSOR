"""Validator pipeline stages.

Each stage is an independent, individually testable function:

    generate -> dispatch -> collect -> validate_schema -> evaluate_correctness
    -> evaluate_evidence -> robustness_probe -> calibration -> latency
    -> final_score -> update_reputation -> emissions

``subnet/validator/validator.py`` merely orchestrates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..miner.simulated import SimulatedMiner
from ..protocol.messages import (Category, EvaluationResult, MinerResponse,
                                 ScoreBreakdown, TaskRequest)
from ..scoring.antigaming import AntiGamingGuard, GuardReport
from ..scoring.components import clamp
from ..scoring.config import DEFAULT_CONFIG, MechanismConfig
from ..scoring.engine import ScoringContext, ScoringEngine
from ..scoring.reputation import MinerReputation
from ..tasks.base import GeneratedTask, GroundTruth
from ..tasks.engine import TaskEngine


@dataclass(slots=True)
class DispatchResult:
    task: GeneratedTask
    responses: List[MinerResponse]
    dropped: List[int]


# --- stage 1: generation ---------------------------------------------------
def generate(engine: TaskEngine, category: Optional[Category], difficulty: int,
             guard: AntiGamingGuard, validator_uid: int) -> GeneratedTask:
    task = engine.generate(category=category, difficulty=difficulty)
    task.request.validator_uid = validator_uid
    guard.register_task(task.request)
    return task


# --- stage 2/3: dispatch + collect ----------------------------------------
def dispatch(task: GeneratedTask, miners: Sequence[SimulatedMiner]) -> DispatchResult:
    """Send the *public* request only. Ground truth is passed to the simulated
    miner separately as its 'own computation' (see subnet/miner/oracle.py)."""
    responses: List[MinerResponse] = []
    dropped: List[int] = []
    for miner in miners:
        r = miner.respond(task.request, task.ground_truth)
        if r is None:
            dropped.append(miner.uid)
        else:
            responses.append(r)
    return DispatchResult(task=task, responses=responses, dropped=dropped)


# --- stage 4: schema + anti-gaming validation ------------------------------
def validate_response(response: MinerResponse, task: TaskRequest,
                      guard: AntiGamingGuard) -> GuardReport:
    return guard.inspect(response, task)


# --- stage 5..9: scoring ---------------------------------------------------
def build_context(reputation: Optional[MinerReputation],
                  guard_report: GuardReport,
                  config: MechanismConfig) -> ScoringContext:
    ctx = ScoringContext(penalties=dict(guard_report.penalties))
    if reputation is not None:
        ctx.confidences = list(reputation.confidences)
        ctx.outcomes = list(reputation.outcomes)
        ctx.probe_outcomes = list(reputation.probe_outcomes)
    return ctx


def score_response(scorer: ScoringEngine, response: MinerResponse,
                   ground_truth: GroundTruth, ctx: ScoringContext) -> ScoreBreakdown:
    return scorer.score(response, ground_truth, ctx)


# --- stage 7: robustness probe --------------------------------------------
def robustness_probe(engine: TaskEngine, task: GeneratedTask,
                     miner: SimulatedMiner, guard: AntiGamingGuard,
                     scorer: ScoringEngine) -> Optional[Tuple[bool, GeneratedTask,
                                                              MinerResponse]]:
    """Issue a semantics-preserving mutation and check the answer still holds."""
    mutated = engine.mutate(task)
    if mutated is None:
        return None
    mutated.request.validator_uid = task.request.validator_uid
    guard.register_task(mutated.request)
    response = miner.respond(mutated.request, mutated.ground_truth)
    if response is None:
        return False, mutated, None  # type: ignore[return-value]
    from ..scoring.components import accuracy_score

    consistent = accuracy_score(response.answer, mutated.ground_truth) >= 1.0
    return consistent, mutated, response


# --- stage 10: consensus ---------------------------------------------------
def consensus(responses: Sequence[MinerResponse],
              breakdowns: Dict[int, ScoreBreakdown],
              reputations: Dict[int, MinerReputation]) -> Dict[str, float]:
    """Reputation-weighted agreement over the answer set.

    Consensus is reported for observability. It is NOT used as ground truth
    for programmatically verifiable categories — otherwise a colluding
    majority could define truth. It only acts as a signal for
    ``VerificationType.CONSENSUS`` tasks and for the UI.
    """
    if not responses:
        return {"agreement": 0.0, "verification_confidence": 0.0, "correct_share": 0.0}
    from ..protocol.signing import response_fingerprint

    buckets: Dict[str, float] = {}
    for r in responses:
        w = 0.1 + (reputations[r.miner_uid].reputation if r.miner_uid in reputations else 0.0)
        buckets[response_fingerprint(r.answer)] = buckets.get(
            response_fingerprint(r.answer), 0.0) + w
    total = sum(buckets.values()) or 1.0
    agreement = max(buckets.values()) / total
    correct = sum(1 for r in responses if breakdowns[r.miner_uid].accuracy >= 1.0)
    correct_share = correct / len(responses)
    # verification confidence blends agreement with how many *verified-correct*
    # answers there are; a task everyone got wrong is not "confidently verified"
    verification_confidence = clamp(0.5 * agreement + 0.5 * correct_share)
    return {
        "agreement": round(agreement, 6),
        "correct_share": round(correct_share, 6),
        "verification_confidence": round(verification_confidence, 6),
    }


# --- stage 11: reputation --------------------------------------------------
def update_reputation(rep: MinerReputation, task: GeneratedTask,
                      response: MinerResponse, breakdown: ScoreBreakdown,
                      probe_outcome: Optional[bool], flags: List[str]) -> None:
    rep.record(task_id=task.task_id, category=task.request.category,
               breakdown=breakdown, confidence=response.confidence,
               latency_ms=response.execution_time_ms,
               probe_outcome=probe_outcome, flags=flags)


# --- stage 12: adaptive difficulty ----------------------------------------
def next_difficulty(score: float, config: MechanismConfig = DEFAULT_CONFIG,
                    rng=None) -> int:
    """Map a miner/network score onto the next difficulty band."""
    import random as _random

    rng = rng or _random.Random()
    d = config.difficulty
    if score < d.easy_below:
        lo, hi = d.easy_range
    elif score < d.normal_below:
        lo, hi = d.normal_range
    elif score < d.hard_below:
        lo, hi = d.hard_range
    else:
        lo, hi = d.adversarial_range
    return rng.randint(lo, hi)


def difficulty_band(score: float, config: MechanismConfig = DEFAULT_CONFIG) -> str:
    d = config.difficulty
    if score < d.easy_below:
        return "easy"
    if score < d.normal_below:
        return "normal"
    if score < d.hard_below:
        return "hard"
    return "adversarial"
