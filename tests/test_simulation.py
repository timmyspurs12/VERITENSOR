"""Miner simulator, validator pipeline and full-network simulation."""

import pytest

from subnet.miner import PROFILES, SimulatedMiner, get_profile
from subnet.protocol.messages import Category, TaskStatus
from subnet.simulation import SimulationConfig, SubnetNetwork
from subnet.tasks import TaskEngine, verify
from subnet.validator import pipeline as P


# ------------------------------------------------------------------ miners
def test_all_profiles_produce_valid_responses(task_engine):
    for key, profile in PROFILES.items():
        miner = SimulatedMiner(1, key, profile, seed=1)
        task = task_engine.generate(difficulty=5)
        r = miner.respond(task.request, task.ground_truth)
        if r is None:
            continue
        assert r.task_id == task.request.task_id
        assert r.nonce == task.request.nonce      # replay-safe echo
        assert 0.0 <= r.confidence <= 1.0
        assert r.execution_time_ms >= 0


def test_profiles_differentiate_accuracy(task_engine):
    tasks = [task_engine.generate(difficulty=5) for _ in range(120)]

    def measure(key):
        miner = SimulatedMiner(1, key, get_profile(key), seed=7)
        hits = 0
        for t in tasks:
            r = miner.respond(t.request, t.ground_truth)
            hits += bool(r and verify(r.answer, t.ground_truth) >= 1.0)
        return hits / len(tasks)

    assert measure("high_quality") > measure("weak") + 0.2
    assert measure("high_quality") > measure("gaming") + 0.4


def test_hallucinating_miner_is_overconfident(task_engine):
    miner = SimulatedMiner(1, "h", get_profile("hallucinating"), seed=3)
    tasks = [task_engine.generate(difficulty=6) for _ in range(60)]
    confs, hits = [], 0
    for t in tasks:
        r = miner.respond(t.request, t.ground_truth)
        if r:
            confs.append(r.confidence)
            hits += verify(r.answer, t.ground_truth) >= 1.0
    assert sum(confs) / len(confs) - hits / len(tasks) > 0.25


def test_miner_without_priming_abstains(task_engine):
    miner = SimulatedMiner(1, "m", get_profile("balanced"), seed=1)
    task = task_engine.generate(difficulty=5)
    r = miner.handle(task.request)          # never primed
    assert r is not None and r.answer == "unknown" and r.confidence < 0.1


# ------------------------------------------------------------------ validator
def test_validator_runs_full_pipeline(network):
    validator = list(network.validators.values())[0]
    record = validator.run_task(list(network.miners.values()),
                               network.reputations, network_score=0.5)
    assert record.status == TaskStatus.SCORED
    assert record.responses
    assert set(record.consensus) == {"agreement", "correct_share",
                                     "verification_confidence"}
    for r in record.responses:
        assert 0.0 <= r.score <= 1.0
        assert set(r.breakdown) >= {"accuracy", "evidence", "robustness",
                                    "calibration", "latency"} or r.rejected


def test_validator_emits_events_for_every_stage(network):
    before = len(network.bus)
    network.step()
    kinds = {e.kind for e in network.bus.recent(200)}
    assert {"task.generated", "task.dispatched", "miner.responded",
            "task.verified"} <= kinds
    assert len(network.bus) > before


def test_adaptive_difficulty_bands():
    from subnet.scoring.config import DEFAULT_CONFIG

    assert P.difficulty_band(0.3, DEFAULT_CONFIG) == "easy"
    assert P.difficulty_band(0.7, DEFAULT_CONFIG) == "normal"
    assert P.difficulty_band(0.85, DEFAULT_CONFIG) == "hard"
    assert P.difficulty_band(0.95, DEFAULT_CONFIG) == "adversarial"
    for score, lo, hi in ((0.2, 1, 3), (0.7, 4, 6), (0.85, 7, 8), (0.97, 9, 10)):
        assert lo <= P.next_difficulty(score) <= hi


def test_robustness_probes_are_issued_and_recorded(network):
    for _ in range(25):
        network.step()
    summary = network.adversarial_summary()
    assert summary["probes"] > 0
    assert 0.0 <= summary["hold_rate"] <= 1.0


# ------------------------------------------------------------------ network
def test_simulation_runs_and_normalises_emissions(network):
    result = network.run_simulation(SimulationConfig(miners=6, validators=2,
                                                     tasks=40,
                                                     difficulty_mode="normal"))
    assert result["tasks_completed"] == 40
    total = sum(r["emission_weight"] for r in result["leaderboard"])
    assert total == pytest.approx(1.0, abs=1e-6) or total == 0.0
    assert result["stats"]["tasks_verified"] >= 40


def test_scale_50_miners_5_validators_100_tasks():
    """Acceptance criterion: the required scale must complete quickly."""
    import time

    net = SubnetNetwork(seed=7)
    net.populate(miners=50, validators=5)
    started = time.perf_counter()
    net.run_simulation(SimulationConfig(miners=50, validators=5, tasks=100,
                                        difficulty_mode="adaptive"))
    elapsed = time.perf_counter() - started
    assert elapsed < 60, f"simulation too slow: {elapsed:.1f}s"
    assert len(net.tasks) == 100
    assert sum(r.emission_weight for r in net.reputations.values()) == \
        pytest.approx(1.0, abs=1e-6)


def test_leaderboard_orders_by_reputation(network):
    network.run_simulation(SimulationConfig(tasks=40, difficulty_mode="normal"))
    board = network.leaderboard()
    assert [r["rank"] for r in board] == list(range(1, len(board) + 1))
    assert board == sorted(board, key=lambda r: r["sort_key"], reverse=True)


def test_category_filter_produces_category_metrics(network):
    network.run_simulation(SimulationConfig(tasks=40, difficulty_mode="normal"))
    board = network.leaderboard(category="math")
    for row in board:
        assert "category_accuracy" in row


def test_reproducible_with_same_seed():
    def run():
        net = SubnetNetwork(seed=4242)
        net.populate(miners=5, validators=2)
        net.run_simulation(SimulationConfig(tasks=25, difficulty_mode="normal",
                                            seed=4242))
        return [round(r["reputation"], 6) for r in net.leaderboard()]

    assert run() == run()


def test_gini_is_bounded(network):
    from subnet.simulation import gini

    assert gini([]) == 0.0
    assert gini([0.5, 0.5]) == pytest.approx(0.0, abs=1e-6)
    assert 0.0 <= gini([1.0, 0.0, 0.0, 0.0]) <= 1.0
