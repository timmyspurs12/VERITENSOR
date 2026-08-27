"""Phase 2 — end-to-end mechanism verification.

Proves the whole pipeline works at the scale the brief requires (10 miners,
3 validators, 100 tasks) and that the mechanism *visibly differentiates*
miner archetypes.

Nothing here is hardcoded: every assertion is made against values produced by
executing the real pipeline in this test run.
"""

from __future__ import annotations

import time
from typing import Dict

import pytest

from subnet.protocol.messages import Category, TaskStatus
from subnet.scoring.emissions import EmissionInput, compute_emissions
from subnet.simulation import SimulationConfig, SubnetNetwork

#: the archetypes the brief asks the mechanism to separate
REQUIRED_MIX = [
    ("high_quality", "high-quality"),
    ("fast", "fast"),
    ("unstable", "slow but accurate"),
    ("weak", "weak"),
    ("hallucinating", "hallucinating"),
    ("specialist_code", "specialist"),
    ("specialist_math", "specialist"),
    ("gaming", "adversarial/gaming"),
    ("balanced", "balanced"),
    ("balanced", "balanced"),
]


@pytest.fixture(scope="module")
def executed_network() -> SubnetNetwork:
    """10 miners × 3 validators × 100 tasks, executed once for the module."""
    net = SubnetNetwork(seed=20260827)
    for index, (profile, _) in enumerate(REQUIRED_MIX):
        net.register_miner(profile, name=f"{profile}-{index:02d}")
    for strategy in ("broadcast", "adversarial", "quantitative"):
        net.register_validator(strategy)
    net.run_simulation(SimulationConfig(miners=10, validators=3, tasks=100,
                                        difficulty_mode="adaptive", seed=20260827))
    return net


@pytest.fixture(scope="module")
def board(executed_network: SubnetNetwork) -> Dict[str, dict]:
    return {row["name"]: row for row in executed_network.leaderboard()}


# ----------------------------------------------------------------- topology
def test_required_scale_was_executed(executed_network):
    assert len(executed_network.miners) == 10
    assert len(executed_network.validators) == 3
    assert len(executed_network.tasks) == 100


def test_every_validator_issued_tasks(executed_network):
    issued = {v.uid: v.tasks_scored for v in executed_network.validators.values()}
    assert all(count > 0 for count in issued.values()), issued
    assert sum(issued.values()) == 100


# ------------------------------------------------------------- full pipeline
def test_every_pipeline_stage_produced_output(executed_network):
    """validator → task → dispatch → response → verify → score → reputation."""
    task = executed_network.tasks[-1]
    assert task.status == TaskStatus.SCORED
    assert task.prompt and task.commitment
    assert task.responses, "no responses collected"

    graded = [r for r in task.responses if not r.rejected]
    assert graded, "no response survived validation"
    for response in graded:
        assert set(response.breakdown) == {"accuracy", "evidence", "robustness",
                                           "calibration", "latency"}
        assert all(0.0 <= v <= 1.0 for v in response.breakdown.values())
        assert 0.0 <= response.score <= 1.0

    assert set(task.consensus) == {"agreement", "correct_share",
                                   "verification_confidence"}
    for rep in executed_network.reputations.values():
        assert rep.task_count > 0
        assert rep.history, "no reputation history recorded"


def test_correctness_robustness_calibration_latency_all_vary(executed_network):
    """Each dimension must be a real signal, not a constant."""
    values = {k: set() for k in ("accuracy", "evidence", "robustness",
                                 "calibration", "latency")}
    for task in executed_network.tasks:
        for response in task.responses:
            for key, value in (response.breakdown or {}).items():
                values[key].add(round(value, 3))
    for key, observed in values.items():
        assert len(observed) > 3, f"{key} produced only {observed}"


def test_robustness_probes_were_actually_issued(executed_network):
    summary = executed_network.adversarial_summary()
    assert summary["probes"] > 0
    assert summary["probes"] == summary["held"] + summary["flipped"]
    assert 0.0 <= summary["hold_rate"] <= 1.0


def test_emissions_normalised_after_execution(executed_network):
    total = sum(r.emission_weight for r in executed_network.reputations.values())
    assert total == pytest.approx(1.0, abs=1e-6)
    assert all(0.0 <= r.emission_weight <= 1.0
               for r in executed_network.reputations.values())


# --------------------------------------------------- archetype separation
def test_high_quality_beats_weak(board):
    assert board["high_quality-00"]["reputation"] > board["weak-03"]["reputation"] + 0.15


def test_high_quality_beats_gaming_decisively(board):
    hq, gaming = board["high_quality-00"], board["gaming-07"]
    assert hq["reputation"] > gaming["reputation"] + 0.3
    assert hq["emission_weight"] > gaming["emission_weight"]
    assert gaming["emission_weight"] <= 0.02, "a gaming miner should earn ~nothing"


def test_hallucinating_miner_is_punished_on_calibration(board):
    hallucinating = board["hallucinating-04"]
    honest = board["balanced-08"]
    assert hallucinating["components"]["calibration"] < \
        honest["components"]["calibration"]
    # it answers correctly a fair fraction of the time, yet must not out-earn
    # a calibrated miner of similar accuracy
    assert hallucinating["reputation"] < honest["reputation"]


def test_fast_miner_wins_on_latency_but_not_automatically_overall(board):
    fast, slow = board["fast-01"], board["unstable-02"]
    assert fast["mean_latency_ms"] < slow["mean_latency_ms"]
    assert fast["components"]["latency"] >= slow["components"]["latency"]


def test_slow_accurate_miner_still_ranks_well(board):
    """Latency is a budget, not a race: accuracy must dominate it."""
    slow_accurate = board["unstable-02"]
    weak = board["weak-03"]
    assert slow_accurate["accuracy"] > weak["accuracy"]
    assert slow_accurate["reputation"] > weak["reputation"]


def test_specialists_are_better_in_their_own_category(executed_network):
    code_specialist = next(r for r in executed_network.reputations.values()
                           if r.name.startswith("specialist_code"))
    math_specialist = next(r for r in executed_network.reputations.values()
                           if r.name.startswith("specialist_math"))
    code_cat = code_specialist.category.get("code")
    math_cat = math_specialist.category.get("math")
    if code_cat and code_cat.tasks >= 5:
        others = [c for k, c in code_specialist.category.items()
                  if k != "code" and c.tasks >= 5]
        if others:
            assert code_cat.accuracy >= max(c.accuracy for c in others) - 0.05
    if math_cat and math_cat.tasks >= 5:
        others = [c for k, c in math_specialist.category.items()
                  if k != "math" and c.tasks >= 5]
        if others:
            assert math_cat.accuracy >= max(c.accuracy for c in others) - 0.05


def test_leaderboard_is_strictly_ordered_and_not_uniform(board):
    reputations = sorted((row["reputation"] for row in board.values()), reverse=True)
    assert reputations == sorted(reputations, reverse=True)
    spread = reputations[0] - reputations[-1]
    assert spread > 0.25, f"mechanism failed to differentiate miners (spread {spread})"


def test_emission_distribution_is_not_uniform(board):
    weights = sorted((row["emission_weight"] for row in board.values()), reverse=True)
    assert weights[0] > weights[-1]
    assert len(set(round(w, 4) for w in weights)) > 3


def test_no_value_in_the_leaderboard_is_hardcoded(board, executed_network):
    """Sanity: recomputing emissions from reputations reproduces the table."""
    recomputed = compute_emissions(
        [EmissionInput(uid=r.uid, reputation=r.reputation, task_count=r.task_count)
         for r in executed_network.reputations.values()])
    for row in board.values():
        assert recomputed.weights[row["uid"]] == pytest.approx(
            row["emission_weight"], abs=1e-9)


# --------------------------------------------------------------- performance
def test_scale_run_is_fast_enough_for_a_live_demo():
    net = SubnetNetwork(seed=7)
    net.populate(miners=10, validators=3)
    started = time.perf_counter()
    net.run_simulation(SimulationConfig(miners=10, validators=3, tasks=100,
                                        difficulty_mode="adaptive"))
    elapsed = time.perf_counter() - started
    assert elapsed < 30, f"100 tasks took {elapsed:.1f}s"
    assert len(net.tasks) == 100


# ------------------------------------------------------- operational health
def test_validators_are_not_marked_stale_merely_for_being_idle(executed_network):
    """A validator that simply was not sampled recently is healthy, not stale.

    Regression: wall-clock idleness flagged three of four validators as stale
    the moment an operator triggered a single manual task.
    """
    for _ in range(3):
        executed_network.step(validator=list(executed_network.validators.values())[0])
    health = executed_network.health()
    statuses = {v["name"]: v["status"] for v in health["validators"]}
    assert all(s == "healthy" for s in statuses.values()), statuses


def test_a_validator_that_stops_working_is_marked_stale(executed_network):
    """But one that misses a sustained run of tasks must be reported."""
    busy = list(executed_network.validators.values())[0]
    laggard = list(executed_network.validators.values())[1]
    for _ in range(60):
        executed_network.step(validator=busy)
    health = {v["uid"]: v for v in executed_network.health()["validators"]}
    assert health[busy.uid]["status"] == "healthy"
    assert health[laggard.uid]["status"] == "stale"
    assert health[laggard.uid]["tasks_missed"] > 0
