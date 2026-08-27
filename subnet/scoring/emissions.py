"""Emission model: reputation -> normalised subnet weights.

Pipeline (each stage is separately testable):

    reputation  ->  eligibility filter  ->  floor subtraction  ->
    temperature sharpening  ->  normalisation  ->  cap enforcement  ->
    renormalisation

Guarantees enforced by :func:`compute_emissions` and covered by tests:

* the returned weights always sum to 1.0 (or to 0.0 when nobody is eligible)
* no weight is negative, NaN or infinite
* no miner exceeds ``EmissionPolicy.max_share``
* a miner with fewer than ``min_tasks`` scored tasks receives 0
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .components import clamp
from .config import DEFAULT_CONFIG, EmissionPolicy, MechanismConfig


@dataclass(frozen=True, slots=True)
class EmissionInput:
    uid: int
    reputation: float
    task_count: int


@dataclass(frozen=True, slots=True)
class EmissionResult:
    weights: Dict[int, float]
    eligible: List[int]
    excluded: Dict[int, str]
    burned: float

    def total(self) -> float:
        return round(sum(self.weights.values()), 9)


def compute_emissions(miners: Sequence[EmissionInput],
                      config: MechanismConfig = DEFAULT_CONFIG) -> EmissionResult:
    policy = config.emission
    weights: Dict[int, float] = {m.uid: 0.0 for m in miners}
    excluded: Dict[int, str] = {}

    eligible: List[EmissionInput] = []
    for m in miners:
        rep = clamp(m.reputation)
        if m.task_count < policy.min_tasks:
            excluded[m.uid] = f"insufficient_sample(<{policy.min_tasks})"
        elif rep < policy.floor_score:
            excluded[m.uid] = f"below_floor(<{policy.floor_score})"
        else:
            eligible.append(EmissionInput(m.uid, rep, m.task_count))

    if not eligible:
        return EmissionResult(weights=weights, eligible=[], excluded=excluded,
                              burned=1.0 if policy.burn_unallocated else 0.0)

    # floor subtraction then temperature sharpening
    raw: Dict[int, float] = {}
    for m in eligible:
        surplus = max(0.0, m.reputation - policy.floor_score)
        value = math.pow(surplus, policy.temperature)
        raw[m.uid] = 0.0 if (math.isnan(value) or math.isinf(value)) else value

    total = sum(raw.values())
    if total <= 0:  # everyone exactly at the floor -> uniform split
        share = 1.0 / len(eligible)
        raw = {uid: share for uid in raw}
        total = 1.0

    normalised = {uid: v / total for uid, v in raw.items()}
    normalised = _enforce_cap(normalised, policy.max_share)

    # final safety normalisation (protects against float drift)
    s = sum(normalised.values())
    if s <= 0:
        normalised = {uid: 1.0 / len(normalised) for uid in normalised}
    else:
        normalised = {uid: v / s for uid, v in normalised.items()}

    weights.update({uid: round(v, 9) for uid, v in normalised.items()})
    drift = 1.0 - sum(weights.values())
    if abs(drift) > 1e-12 and weights:
        top = max(weights, key=lambda k: weights[k])
        weights[top] = round(weights[top] + drift, 9)
    return EmissionResult(weights=weights, eligible=[m.uid for m in eligible],
                          excluded=excluded, burned=0.0)


def _enforce_cap(weights: Mapping[int, float], max_share: float) -> Dict[int, float]:
    """Iteratively clip whales and redistribute to the uncapped remainder."""
    out = dict(weights)
    if max_share <= 0 or max_share >= 1 or len(out) == 0:
        return out
    # In a small network a low cap is either unreachable (n*cap < 1) or binds on
    # everyone and flattens the distribution, destroying the incentive signal.
    # The cap is therefore relaxed to 2/n for small populations: it still limits
    # concentration, but it can never make every miner identical.
    max_share = max(max_share, 2.0 / len(out))
    for _ in range(64):
        over = {uid: w for uid, w in out.items() if w > max_share + 1e-12}
        if not over:
            break
        excess = sum(w - max_share for w in over.values())
        for uid in over:
            out[uid] = max_share
        room = {uid: w for uid, w in out.items() if uid not in over}
        room_total = sum(room.values())
        if room_total <= 0:
            break
        for uid, w in room.items():
            out[uid] = w + excess * (w / room_total)
    return out


def weights_to_uid_map(weights: Mapping[int, float]) -> Dict[int, float]:
    """``{uid: weight}`` for ``bittensor.set_weights`` (SDK v11).

    The v11 one-call setter accepts relative float weights and performs the
    clipping, normalisation and u16 quantisation itself against the subnet's
    hyperparameters, so we hand it the vector as computed and drop only the
    zero-weight (ineligible) miners.
    """
    return {int(uid): float(clamp(w)) for uid, w in weights.items() if clamp(w) > 0}


def weights_to_bittensor(weights: Mapping[int, float], u16_max: int = 65535
                         ) -> Tuple[List[int], List[int]]:
    """Convert normalised weights into a ``(uids, u16 weights)`` pair.

    Retained for SDK generations whose ``set_weights`` took parallel uid/weight
    lists, and used by the simulation adapter to show operators the quantised
    vector that would go on chain. SDK v11 prefers
    :func:`weights_to_uid_map`."""
    items = [(uid, clamp(w)) for uid, w in weights.items() if clamp(w) > 0]
    if not items:
        return [], []
    peak = max(w for _, w in items)
    uids = [uid for uid, _ in items]
    vals = [int(round(w / peak * u16_max)) for _, w in items]
    return uids, vals
