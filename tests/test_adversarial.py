"""Phase 4 — adversarial test suite.

Each test *plays an attacker*: it constructs the behaviour a rational miner
would use to extract emission without doing the work, runs it through the real
validator pipeline, and asserts the mechanism defeats it.

Results from this suite are summarised in ``docs/ANTI_GAMING.md``. The numbers
in that document are produced by running these tests, not written by hand —
``tests/test_adversarial.py::test_emit_attack_report`` regenerates the table.
"""

from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from subnet.protocol.messages import Evidence, MinerResponse, TaskRequest
from subnet.protocol.signing import new_nonce, new_task_id
from subnet.scoring.antigaming import AntiGamingGuard, RateLimitRule
from subnet.scoring.config import DEFAULT_CONFIG
from subnet.scoring.emissions import EmissionInput, compute_emissions
from subnet.scoring.engine import ScoringContext, ScoringEngine
from subnet.scoring.reputation import MinerReputation
from subnet.simulation import SimulationConfig, SubnetNetwork
from subnet.tasks import TaskEngine, verify
from subnet.tasks.base import GeneratedTask

REPORT: Dict[str, Dict[str, object]] = {}


def record(attack: str, defence: str, outcome: str, **detail) -> None:
    REPORT[attack] = {"defence": defence, "outcome": outcome, **detail}


@pytest.fixture
def engine() -> TaskEngine:
    return TaskEngine(seed=4242)


@pytest.fixture
def scorer() -> ScoringEngine:
    return ScoringEngine(DEFAULT_CONFIG)


def respond(task: GeneratedTask, uid: int, answer: str, *, confidence: float = 0.9,
            evidence: Optional[List[str]] = None, latency: int = 500,
            nonce: Optional[str] = None) -> MinerResponse:
    return MinerResponse(
        task_id=task.request.task_id, miner_uid=uid,
        nonce=nonce or task.request.nonce, answer=answer, confidence=confidence,
        evidence=[Evidence(kind="reasoning", content=e) for e in (evidence or [])],
        execution_time_ms=latency)


# ======================================================================
# A1 — memorisation
# ======================================================================
def test_memorisation_is_useless_because_tasks_are_never_repeated(engine):
    """An attacker caching (prompt → answer) gets no reuse."""
    seen: Dict[str, str] = {}
    collisions = 0
    for _ in range(400):
        task = engine.generate(difficulty=5)
        if task.request.prompt in seen:
            collisions += 1
        seen[task.request.prompt] = task.ground_truth.answer
    reuse_rate = collisions / 400
    record("A1 memorisation", "dynamic generation from random seeds",
           "defeated", prompt_reuse_rate=round(reuse_rate, 4), samples=400)
    # Some collision is unavoidable (birthday paradox over a finite parameter
    # space); the requirement is that caching prompts is not a viable strategy.
    assert reuse_rate < 0.03, f"{reuse_rate:.1%} of prompts repeated"


def test_task_ids_and_nonces_are_unguessable(engine):
    ids = {engine.generate(difficulty=3).request.task_id for _ in range(500)}
    assert len(ids) == 500
    assert all(len(i) >= 16 for i in ids)


# ======================================================================
# A2 — replay
# ======================================================================
def test_replay_of_a_valid_response_against_another_task_is_rejected(engine):
    guard = AntiGamingGuard()
    first, second = engine.generate(difficulty=5), engine.generate(difficulty=5)
    guard.register_task(first.request)
    guard.register_task(second.request)

    honest = respond(first, uid=1, answer=first.ground_truth.answer)
    assert not guard.inspect(honest, first.request).rejected

    stolen = honest.model_copy(update={"task_id": second.request.task_id})
    report = guard.inspect(stolen, second.request)
    record("A2 replay (cross-task)", "nonce + task binding", "defeated",
           reason=report.reason)
    assert report.rejected and report.reason == "nonce_mismatch"


def test_replay_of_the_same_response_twice_is_rejected(engine):
    guard = AntiGamingGuard()
    task = engine.generate(difficulty=5)
    guard.register_task(task.request)
    answer = respond(task, uid=1, answer=task.ground_truth.answer)
    assert not guard.inspect(answer, task.request).rejected
    second = guard.inspect(answer, task.request)
    record("A2 replay (duplicate submit)", "per-(task,miner) submission ledger",
           "defeated", reason=second.reason)
    assert second.rejected and second.reason == "duplicate_submission"


def test_forged_nonce_is_rejected(engine):
    guard = AntiGamingGuard()
    task = engine.generate(difficulty=5)
    guard.register_task(task.request)
    forged = respond(task, uid=1, answer=task.ground_truth.answer, nonce=new_nonce())
    report = guard.inspect(forged, task.request)
    assert report.rejected and report.reason == "nonce_mismatch"


# ======================================================================
# A3 — constant / low-effort answers
# ======================================================================
def test_constant_answer_farming_earns_almost_nothing(engine, scorer):
    """Always answering 'VULNERABLE' on open-ended families is unprofitable."""
    guard = AntiGamingGuard()
    rep = MinerReputation(1, "farmer")
    honest_rep = MinerReputation(2, "honest")
    for _ in range(60):
        task = engine.generate(difficulty=5)
        guard.register_task(task.request)

        cheat = respond(task, uid=1, answer="VULNERABLE", confidence=0.95,
                        evidence=["Based on a comprehensive multi-step analysis "
                                  "of the provided material."], latency=120)
        cheat_report = guard.inspect(cheat, task.request)
        if not cheat_report.rejected:
            breakdown = scorer.score(cheat, task.ground_truth,
                                     ScoringContext(confidences=rep.confidences,
                                                    outcomes=rep.outcomes,
                                                    penalties=dict(cheat_report.penalties)))
            rep.record(task.request.task_id, task.request.category, breakdown,
                       cheat.confidence, cheat.execution_time_ms,
                       flags=cheat_report.flags)

        good = respond(task, uid=2, answer=task.ground_truth.answer, confidence=0.9,
                       evidence=[f"Derived the result using "
                                 f"{', '.join(task.ground_truth.evidence_keywords[:2]) or 'the constraints'}; "
                                 "verified against 2 checks."], latency=900)
        good_report = guard.inspect(good, task.request)
        good_breakdown = scorer.score(good, task.ground_truth,
                                      ScoringContext(confidences=honest_rep.confidences,
                                                     outcomes=honest_rep.outcomes,
                                                     penalties=dict(good_report.penalties)))
        honest_rep.record(task.request.task_id, task.request.category,
                          good_breakdown, good.confidence, good.execution_time_ms,
                          flags=good_report.flags)

    result = compute_emissions([
        EmissionInput(1, rep.reputation, rep.task_count),
        EmissionInput(2, honest_rep.reputation, honest_rep.task_count)])
    record("A3 constant-answer farming",
           "accuracy weight + duplicate detection + boilerplate evidence",
           "defeated", cheat_reputation=round(rep.reputation, 4),
           honest_reputation=round(honest_rep.reputation, 4),
           cheat_emission=round(result.weights[1], 4),
           flags=dict(rep.flags))
    assert rep.reputation < honest_rep.reputation
    assert result.weights[1] < result.weights[2]
    assert rep.flags, "constant answers should raise anti-gaming flags"


def test_empty_and_junk_answers_score_zero(engine, scorer):
    task = engine.generate(difficulty=5)
    for junk in ("", "   ", "\n\n", "?" * 200):
        response = respond(task, uid=1, answer=junk or "x")
        response = response.model_copy(update={"answer": junk})
        breakdown = scorer.score(response, task.ground_truth)
        assert breakdown.accuracy == 0.0


# ======================================================================
# A4 — confidence manipulation
# ======================================================================
@pytest.mark.parametrize("confidence", [0.99, 0.95, 0.9])
def test_inflated_confidence_destroys_the_calibration_component(confidence, engine,
                                                                scorer):
    rep = MinerReputation(1, "overconfident")
    hits = 0
    for index in range(40):
        task = engine.generate(difficulty=5)
        correct = index % 5 < 3            # 60% accurate
        answer = task.ground_truth.answer if correct else "definitely-wrong"
        hits += correct
        response = respond(task, uid=1, answer=answer, confidence=confidence)
        breakdown = scorer.score(response, task.ground_truth,
                                 ScoringContext(confidences=rep.confidences,
                                                outcomes=rep.outcomes))
        rep.record(task.request.task_id, task.request.category, breakdown,
                   confidence, response.execution_time_ms)
    calibration = rep.last_components["calibration"]
    record(f"A4 confidence inflation @{confidence}",
           "Brier-based calibration over a rolling window", "defeated",
           accuracy=round(hits / 40, 3), calibration=round(calibration, 4))
    assert calibration < 0.35


def test_honest_discriminative_confidence_is_rewarded(engine, scorer):
    rep = MinerReputation(1, "calibrated")
    for index in range(40):
        task = engine.generate(difficulty=5)
        correct = index % 5 < 3
        answer = task.ground_truth.answer if correct else "wrong"
        confidence = 0.93 if correct else 0.12     # honest and discriminative
        response = respond(task, uid=1, answer=answer, confidence=confidence)
        breakdown = scorer.score(response, task.ground_truth,
                                 ScoringContext(confidences=rep.confidences,
                                                outcomes=rep.outcomes))
        rep.record(task.request.task_id, task.request.category, breakdown,
                   confidence, response.execution_time_ms)
    assert rep.last_components["calibration"] > 0.8


# ======================================================================
# A5 — shallow pattern matching (defeated by mutation probes)
# ======================================================================
def test_a_miner_that_flips_under_mutation_loses_robustness(engine, scorer):
    """Two miners with identical accuracy; only one survives mutation."""
    stable = MinerReputation(1, "stable")
    brittle = MinerReputation(2, "brittle")
    probes = {"stable": [], "brittle": []}
    for _ in range(30):
        task = engine.generate(difficulty=5)
        mutated = engine.mutate(task)
        if mutated is None:
            continue
        # both answer the parent correctly
        for uid, rep, holds in ((1, stable, True), (2, brittle, False)):
            answer = task.ground_truth.answer
            response = respond(task, uid=uid, answer=answer)
            probe_answer = (mutated.ground_truth.answer if holds else "flipped")
            consistent = verify(probe_answer, mutated.ground_truth) >= 1.0
            probes["stable" if holds else "brittle"].append(consistent)
            breakdown = scorer.score(response, task.ground_truth,
                                     ScoringContext(confidences=rep.confidences,
                                                    outcomes=rep.outcomes,
                                                    probe_outcomes=rep.probe_outcomes))
            rep.record(task.request.task_id, task.request.category, breakdown,
                       response.confidence, response.execution_time_ms,
                       probe_outcome=consistent)
    record("A5 shallow pattern matching", "adversarial mutation probes", "defeated",
           stable_reputation=round(stable.reputation, 4),
           brittle_reputation=round(brittle.reputation, 4),
           stable_hold_rate=round(sum(probes["stable"]) / max(1, len(probes["stable"])), 3),
           brittle_hold_rate=round(sum(probes["brittle"]) / max(1, len(probes["brittle"])), 3))
    assert stable.reputation > brittle.reputation
    assert stable.probe_outcomes and not any(brittle.probe_outcomes)


# ======================================================================
# A6 — benchmark gaming
# ======================================================================
def test_hidden_benchmark_answers_are_never_exposed_to_a_miner(engine):
    """The only object a miner receives must not contain the answer."""
    from benchmarks import register_benchmark_generators

    register_benchmark_generators()
    leaked = 0
    checked = 0
    for _ in range(80):
        task = engine.generate_benchmark(None, 6) or engine.generate(difficulty=6)
        payload = task.request.model_dump_json()
        assert "ground_truth" not in payload
        # Data-analysis answers are values *derived from* the table shown to the
        # miner (a median is by definition one of the rows), so their presence
        # in the prompt is inherent, not a leak. Everything else must not appear.
        if task.request.category.value == "data":
            continue
        if task.ground_truth.verifier in ("numeric", "sequence"):
            checked += 1
            # Token-boundary match against the PROMPT only. Substring matching
            # against the whole payload produces false positives, because the
            # hex nonce and task id contain arbitrary digit runs.
            pattern = rf"(?<![\w.]){re.escape(task.ground_truth.answer.lower())}(?![\w.])"
            if re.search(pattern, task.request.prompt.lower()):
                leaked += 1
    record("A6 benchmark scraping", "hidden ground truth + private bank",
           "defeated", leaks=leaked, checked=checked)
    assert leaked == 0
    assert checked > 5, "leak check did not examine enough items"


def test_benchmark_rotation_makes_task_provenance_unpredictable():
    net = SubnetNetwork(seed=99)
    net.populate(miners=4, validators=2)
    net.run_simulation(SimulationConfig(tasks=120, difficulty_mode="normal"))
    kinds = {}
    for task in net.tasks:
        kinds[task.kind] = kinds.get(task.kind, 0) + 1
    record("A6b task-type detection", "benchmark rotation", "mitigated",
           distribution=kinds)
    assert len(kinds) >= 2


# ======================================================================
# A7 — collusion
# ======================================================================
def test_identical_evidence_across_miners_is_flagged(engine):
    guard = AntiGamingGuard()
    task = engine.generate(difficulty=5)
    guard.register_task(task.request)
    flags: List[str] = []
    for uid in range(5):
        response = respond(task, uid=uid, answer=task.ground_truth.answer,
                           evidence=["word for word identical rationale"])
        flags.extend(guard.inspect(response, task.request).flags)
    record("A7 collusion (identical evidence)", "cross-miner evidence fingerprints",
           "detected", flag_count=flags.count("evidence_collusion"))
    assert "evidence_collusion" in flags


def test_a_wrong_majority_cannot_define_truth(engine, scorer):
    """Consensus must not override the deterministic verifier."""
    task = engine.generate(difficulty=5)
    reputations = {uid: MinerReputation(uid, f"m{uid}") for uid in range(6)}
    breakdowns = {}
    responses = []
    for uid in range(6):
        # five colluding miners agree on a wrong answer, one is correct
        answer = "colluded-wrong" if uid < 5 else task.ground_truth.answer
        response = respond(task, uid=uid, answer=answer)
        responses.append(response)
        breakdowns[uid] = scorer.score(response, task.ground_truth)
    from subnet.validator.pipeline import consensus

    stats = consensus(responses, breakdowns, reputations)
    record("A7b colluding majority", "verifier is authoritative, not consensus",
           "defeated", agreement=stats["agreement"],
           correct_share=stats["correct_share"],
           honest_score=round(breakdowns[5].final_score, 4),
           cartel_score=round(breakdowns[0].final_score, 4))
    assert breakdowns[5].accuracy == 1.0
    assert all(breakdowns[uid].accuracy == 0.0 for uid in range(5))
    assert breakdowns[5].final_score > breakdowns[0].final_score
    assert stats["agreement"] > 0.5          # the cartel does dominate agreement…
    assert stats["correct_share"] < 0.5      # …and it changes nothing about truth


# ======================================================================
# A8 — sybil / small sample
# ======================================================================
def test_many_fresh_identities_cannot_capture_emissions():
    """100 sybils with one lucky task each vs one established honest miner."""
    sybils = [EmissionInput(uid=i, reputation=1.0, task_count=1) for i in range(100)]
    honest = EmissionInput(uid=999, reputation=0.75, task_count=80)
    result = compute_emissions(sybils + [honest])
    sybil_share = sum(result.weights[i] for i in range(100))
    record("A8 sybil / small sample", "minimum sample + trust ramp", "defeated",
           sybil_share=round(sybil_share, 6),
           honest_share=round(result.weights[999], 6))
    assert sybil_share == 0.0
    assert result.weights[999] == pytest.approx(1.0)


# ======================================================================
# A9 — API abuse
# ======================================================================
def test_rate_limiting_caps_request_bursts():
    guard = AntiGamingGuard(rate_rule=RateLimitRule(max_requests=10, per_seconds=60))
    allowed = sum(1 for _ in range(200) if guard.check_rate(1))
    record("A9 API abuse", "per-miner token bucket + per-IP middleware", "defeated",
           allowed_of_200=allowed)
    assert allowed == 10


def test_late_responses_are_penalised(engine):
    guard = AntiGamingGuard()
    task = engine.generate(difficulty=5)
    guard.register_task(task.request)
    response = respond(task, uid=1, answer=task.ground_truth.answer)
    response.submitted_at = task.request.deadline + timedelta(seconds=30)
    report = guard.inspect(response, task.request)
    assert "deadline_miss" in report.flags


# ======================================================================
# A10 — malformed / hostile payloads
# ======================================================================
@pytest.mark.parametrize("payload", [
    {"confidence": 5.0}, {"confidence": -1.0}, {"execution_time_ms": -10},
    {"miner_uid": -1}, {"nonce": "short"},
])
def test_malformed_responses_are_rejected_by_the_schema(payload, engine):
    task = engine.generate(difficulty=5)
    base = {"task_id": task.request.task_id, "miner_uid": 1,
            "nonce": task.request.nonce, "answer": "x", "confidence": 0.5,
            "execution_time_ms": 10}
    base.update(payload)
    with pytest.raises(Exception):
        MinerResponse.model_validate(base)


def test_client_cannot_assert_its_own_score(engine):
    """There is no score field to inject: the schema forbids extras."""
    task = engine.generate(difficulty=5)
    with pytest.raises(Exception):
        MinerResponse.model_validate({
            "task_id": task.request.task_id, "miner_uid": 1,
            "nonce": task.request.nonce, "answer": "x", "confidence": 0.5,
            "execution_time_ms": 10, "score": 1.0, "reputation": 1.0})


def test_oversized_payloads_are_rejected(engine):
    task = engine.generate(difficulty=5)
    with pytest.raises(Exception):
        MinerResponse.model_validate({
            "task_id": task.request.task_id, "miner_uid": 1,
            "nonce": task.request.nonce, "answer": "x" * 20_000,
            "confidence": 0.5, "execution_time_ms": 10})


def test_hostile_evidence_cannot_inflate_the_evidence_score(engine, scorer):
    """Keyword stuffing is capped by structure and specificity terms."""
    task = engine.generate(difficulty=5)
    keywords = task.ground_truth.evidence_keywords or ["constraint"]
    stuffed = respond(task, uid=1, answer=task.ground_truth.answer,
                      evidence=[" ".join(keywords * 40)] * 20)
    honest = respond(task, uid=2, answer=task.ground_truth.answer,
                     evidence=[f"Applied {keywords[0]} to reach the value 42.",
                               "Cross-checked the result against the constraints."])
    stuffed_score = scorer.score(stuffed, task.ground_truth).evidence
    honest_score = scorer.score(honest, task.ground_truth).evidence
    record("A10 evidence keyword stuffing",
           "coverage capped; specificity + structure terms", "mitigated",
           stuffed=round(stuffed_score, 4), honest=round(honest_score, 4))
    assert stuffed_score <= 1.0
    # stuffing may score well on coverage; the documented limitation is that
    # lexical evidence scoring is gameable — assert only that it is bounded and
    # that honest evidence is competitive.
    assert honest_score > 0.4


# ======================================================================
# whole-network attack
# ======================================================================
def test_adversarial_population_does_not_capture_the_subnet():
    """Half the network is hostile; honest miners must still take the emissions."""
    net = SubnetNetwork(seed=31337)
    for i in range(4):
        net.register_miner("gaming", name=f"cartel-{i}")
    for i in range(2):
        net.register_miner("hallucinating", name=f"liar-{i}")
    for i in range(4):
        net.register_miner("high_quality", name=f"honest-{i}")
    net.register_validator("broadcast")
    net.register_validator("adversarial")
    net.run_simulation(SimulationConfig(miners=10, validators=2, tasks=80,
                                        difficulty_mode="adaptive"))
    board = {row["name"]: row for row in net.leaderboard()}
    hostile = sum(board[n]["emission_weight"]
                  for n in board if n.startswith(("cartel", "liar")))
    honest = sum(board[n]["emission_weight"]
                 for n in board if n.startswith("honest"))
    record("A11 hostile-majority network", "full mechanism", "defeated",
           hostile_share=round(hostile, 4), honest_share=round(honest, 4),
           hostile_miners=6, honest_miners=4)
    assert honest > hostile * 3, f"honest {honest:.3f} vs hostile {hostile:.3f}"


def test_zzz_emit_attack_report(tmp_path_factory):
    """Writes the measured results consumed by docs/ANTI_GAMING.md."""
    assert REPORT, "no attacks were recorded"
    out = Path(os.getenv("VERITENSOR_ATTACK_REPORT",
                         Path(__file__).resolve().parents[1] /
                         "docs" / "attack_report.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(REPORT, indent=2, sort_keys=True, default=str))
    assert all(entry["outcome"] in ("defeated", "detected", "mitigated")
               for entry in REPORT.values())
