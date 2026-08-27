"""Emission normalisation invariants."""

import math

import pytest

from subnet.scoring import DEFAULT_CONFIG, EmissionInput, compute_emissions
from subnet.scoring.config import EmissionPolicy, MechanismConfig
from subnet.scoring.emissions import weights_to_bittensor


def inputs(*triples):
    return [EmissionInput(uid=u, reputation=r, task_count=n) for u, r, n in triples]


def test_weights_sum_to_one():
    result = compute_emissions(inputs((1, 0.9, 50), (2, 0.7, 50), (3, 0.5, 50)))
    assert result.total() == pytest.approx(1.0, abs=1e-9)


def test_no_miner_exceeds_max_share():
    cfg = MechanismConfig(emission=EmissionPolicy(max_share=0.25, min_tasks=1))
    result = compute_emissions(
        inputs((1, 0.99, 50), *[(i, 0.30, 50) for i in range(2, 12)]), cfg)
    assert max(result.weights.values()) <= 0.25 + 1e-9
    assert result.total() == pytest.approx(1.0, abs=1e-9)


def test_single_miner_cannot_exceed_100_percent():
    result = compute_emissions(inputs((1, 1.0, 100)))
    assert result.weights[1] <= 1.0 + 1e-12
    assert result.total() == pytest.approx(1.0, abs=1e-9)


def test_small_sample_is_excluded():
    result = compute_emissions(inputs((1, 0.99, 1), (2, 0.6, 50)))
    assert result.weights[1] == 0.0
    assert "insufficient_sample" in result.excluded[1]
    assert result.weights[2] == pytest.approx(1.0)


def test_below_floor_is_excluded():
    result = compute_emissions(inputs((1, 0.10, 50), (2, 0.60, 50)))
    assert result.weights[1] == 0.0
    assert "below_floor" in result.excluded[1]


def test_no_eligible_miners_yields_zero_not_nan():
    result = compute_emissions(inputs((1, 0.05, 50), (2, 0.02, 50)))
    assert result.total() == 0.0
    assert all(w == 0.0 for w in result.weights.values())


def test_empty_population_is_safe():
    result = compute_emissions([])
    assert result.weights == {} and result.total() == 0.0


def test_nan_reputation_cannot_corrupt_emissions():
    result = compute_emissions(inputs((1, float("nan"), 50), (2, 0.8, 50)))
    assert all(math.isfinite(w) for w in result.weights.values())
    assert result.weights[1] == 0.0
    assert result.total() == pytest.approx(1.0, abs=1e-9)


def test_negative_reputation_is_clamped():
    result = compute_emissions(inputs((1, -5.0, 50), (2, 0.8, 50)))
    assert result.weights[1] == 0.0
    assert all(w >= 0 for w in result.weights.values())


def test_better_miner_receives_more_emission():
    result = compute_emissions(inputs((1, 0.90, 50), (2, 0.60, 50), (3, 0.40, 50)))
    assert result.weights[1] > result.weights[2] > result.weights[3]


def test_temperature_sharpens_distribution():
    flat = compute_emissions(
        inputs((1, 0.9, 50), (2, 0.6, 50)),
        MechanismConfig(emission=EmissionPolicy(temperature=1.0, max_share=1.0)))
    sharp = compute_emissions(
        inputs((1, 0.9, 50), (2, 0.6, 50)),
        MechanismConfig(emission=EmissionPolicy(temperature=4.0, max_share=1.0)))
    assert sharp.weights[1] > flat.weights[1]


def test_bittensor_weight_conversion_is_u16_bounded():
    uids, vals = weights_to_bittensor({1: 0.5, 2: 0.25, 3: 0.0})
    assert uids == [1, 2]
    assert vals == [65535, 32768] or vals == [65535, 32767]
    assert all(0 <= v <= 65535 for v in vals)


def test_all_equal_reputations_split_evenly():
    result = compute_emissions(inputs(*[(i, 0.7, 50) for i in range(8)]))
    assert len(set(round(w, 6) for w in result.weights.values())) == 1
    assert result.total() == pytest.approx(1.0, abs=1e-9)
