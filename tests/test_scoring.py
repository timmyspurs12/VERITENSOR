"""Scoring engine, calibration, robustness, reputation smoothing."""

import math

import pytest

from subnet.protocol.messages import Category, Evidence, MinerResponse
from subnet.scoring import (DEFAULT_CONFIG, MechanismConfig, ScoreWeights,
                            ScoringContext, ScoringEngine, brier_score,
                            calibration_score, latency_score, robustness_score)
from subnet.scoring.components import clamp, evidence_score
from subnet.scoring.reputation import MinerReputation
from subnet.tasks.base import GroundTruth


def make_response(answer="42", confidence=0.9, latency=800, evidence=None):
    return MinerResponse(
        task_id="vt_test", miner_uid=1, nonce="0" * 32, answer=answer,
        confidence=confidence, execution_time_ms=latency,
        evidence=[Evidence(kind="reasoning", content=e) for e in (evidence or [])])


GT = GroundTruth(answer="42", verifier="numeric",
                 params={"atol": 0.0, "rtol": 0.0},
                 evidence_keywords=["modulo", "loop"])


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        MechanismConfig(weights=ScoreWeights(accuracy=0.9, evidence=0.9,
                                             robustness=0.0, calibration=0.0,
                                             latency=0.0))


def test_final_score_matches_manual_arithmetic():
    engine = ScoringEngine(DEFAULT_CONFIG)
    b = engine.score(make_response(evidence=["used modulo inside the loop, 42"]), GT)
    w = DEFAULT_CONFIG.weights
    expected = (b.accuracy * w.accuracy + b.evidence * w.evidence
                + b.robustness * w.robustness + b.calibration * w.calibration
                + b.latency * w.latency)
    assert b.final_score == pytest.approx(expected, abs=1e-9)
    assert 0.0 <= b.final_score <= 1.0
    assert sum(r["contribution"] for r in b.explain()) == pytest.approx(expected, abs=1e-6)


def test_all_components_bounded_for_adversarial_inputs():
    engine = ScoringEngine(DEFAULT_CONFIG)
    b = engine.score(make_response(answer="x" * 5000, confidence=1.0,
                                   latency=600_000, evidence=["!" * 100]), GT)
    for value in (b.accuracy, b.evidence, b.robustness, b.calibration,
                  b.latency, b.final_score):
        assert 0.0 <= value <= 1.0 and math.isfinite(value)


def test_score_can_never_be_negative_even_with_huge_penalties():
    engine = ScoringEngine(DEFAULT_CONFIG)
    ctx = ScoringContext(penalties={"a": 5.0, "b": 5.0})
    b = engine.score(make_response(), GT, ctx)
    assert b.final_score >= 0.0


def test_wrong_answer_loses_accuracy_weight():
    engine = ScoringEngine(DEFAULT_CONFIG)
    right = engine.score(make_response("42"), GT).final_score
    wrong = engine.score(make_response("41"), GT).final_score
    assert right - wrong == pytest.approx(DEFAULT_CONFIG.weights.accuracy, abs=0.02)


# ------------------------------------------------------------------ calibration
def test_overconfident_miner_is_penalised():
    """0.95 confidence with 60% accuracy must score worse than honest 0.6."""
    conf_over = [0.95] * 50
    outcomes = [1.0] * 30 + [0.0] * 20
    conf_honest = [0.6] * 50
    over = calibration_score(conf_over, outcomes, DEFAULT_CONFIG.calibration)
    honest = calibration_score(conf_honest, outcomes, DEFAULT_CONFIG.calibration)
    assert over < honest


def test_discriminative_confidence_beats_flat_confidence():
    outcomes = [1.0] * 30 + [0.0] * 20
    sharp = [0.95] * 30 + [0.1] * 20
    flat = [0.6] * 50
    assert calibration_score(sharp, outcomes, DEFAULT_CONFIG.calibration) > \
        calibration_score(flat, outcomes, DEFAULT_CONFIG.calibration) + 0.3


def test_brier_matches_definition():
    assert brier_score([1.0, 0.0], [1.0, 0.0]) == 0.0
    assert brier_score([0.5, 0.5], [1.0, 0.0]) == pytest.approx(0.25)


def test_calibration_uses_prior_before_min_samples():
    p = DEFAULT_CONFIG.calibration
    assert calibration_score([0.9] * (p.min_samples - 1), [1.0] * (p.min_samples - 1),
                             p) == p.prior


def test_calibration_is_bounded():
    assert 0.0 <= calibration_score([1.0] * 20, [0.0] * 20,
                                    DEFAULT_CONFIG.calibration) <= 1.0


# ------------------------------------------------------------------ robustness
def test_robustness_rewards_consistency():
    held = robustness_score([True] * 12, DEFAULT_CONFIG.robustness)
    flipped = robustness_score([False] * 12, DEFAULT_CONFIG.robustness)
    assert held > 0.85 and flipped < 0.05


def test_robustness_prior_when_untested():
    assert robustness_score([], DEFAULT_CONFIG.robustness) == \
        DEFAULT_CONFIG.robustness.prior


# ------------------------------------------------------------------ latency
def test_latency_budget_curve():
    p = DEFAULT_CONFIG.latency
    assert latency_score(10, p) == 1.0
    assert latency_score(p.target_ms, p) == 1.0
    assert latency_score(p.timeout_ms + 5000, p) == p.floor
    mid = latency_score((p.target_ms + p.timeout_ms) // 2, p)
    assert 0.4 < mid < 0.6


# ------------------------------------------------------------------ evidence
def test_boilerplate_evidence_scores_near_zero():
    gt = GroundTruth(answer="x", evidence_keywords=["modulo"])
    score = evidence_score(
        [Evidence(kind="reasoning",
                  content="Based on a comprehensive multi-step analysis ...")],
        gt, DEFAULT_CONFIG.evidence)
    assert score <= 0.05


def test_relevant_evidence_beats_empty_evidence():
    gt = GroundTruth(answer="x", evidence_keywords=["modulo", "loop"])
    good = evidence_score([Evidence(kind="reasoning",
                                    content="Traced the loop and applied modulo 7 twice")],
                          gt, DEFAULT_CONFIG.evidence)
    assert good > evidence_score([], gt, DEFAULT_CONFIG.evidence)


# ------------------------------------------------------------------ reputation
def test_single_lucky_task_cannot_dominate_reputation():
    rep = MinerReputation(1, "fresh")
    engine = ScoringEngine(DEFAULT_CONFIG)
    b = engine.score(make_response(evidence=["modulo loop 42"]), GT)
    rep.record("t1", Category.MATH, b, 0.9, 500)
    assert rep.reputation < 0.5, "one perfect task should not yield a top reputation"


def test_reputation_converges_with_sample_size():
    rep = MinerReputation(1, "steady")
    engine = ScoringEngine(DEFAULT_CONFIG)
    for i in range(60):
        b = engine.score(make_response(evidence=["modulo loop 42"]), GT,
                         ScoringContext(confidences=rep.confidences,
                                        outcomes=rep.outcomes,
                                        probe_outcomes=[True] * 5))
        rep.record(f"t{i}", Category.MATH, b, 0.9, 500, probe_outcome=True)
    assert rep.reputation > 0.7
    assert rep.task_count == 60
    assert len(rep.history) == 60


def test_clamp_rejects_nan_and_inf():
    assert clamp(float("nan")) == 0.0
    assert clamp(float("inf")) == 0.0  # non-finite values collapse to the floor
    assert clamp(float("-inf")) == 0.0
    assert clamp("not a number") == 0.0
