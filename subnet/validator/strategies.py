"""Validator strategies: how a validator picks tasks, miners and probes."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..protocol.messages import Category


@dataclass(frozen=True, slots=True)
class ValidatorStrategy:
    key: str
    label: str
    description: str
    #: category sampling weights; empty = uniform over all categories
    category_weights: Dict[str, float] = field(default_factory=dict)
    #: fraction of the miner set queried per task (1.0 = broadcast)
    sample_fraction: float = 1.0
    #: probability of following a correct answer with a mutation probe
    probe_rate: float = 0.35
    #: how strongly this validator follows adaptive difficulty (0 = fixed)
    adaptivity: float = 1.0
    #: fixed difficulty when adaptivity == 0
    fixed_difficulty: int = 5

    def pick_category(self, rng: random.Random) -> Optional[Category]:
        if not self.category_weights:
            return rng.choice(list(Category))
        items = [(Category(k), v) for k, v in self.category_weights.items()]
        total = sum(v for _, v in items)
        r = rng.random() * total
        upto = 0.0
        for cat, w in items:
            upto += w
            if r <= upto:
                return cat
        return items[-1][0]

    def sample_miners(self, miners: Sequence, rng: random.Random) -> List:
        if self.sample_fraction >= 1.0:
            return list(miners)
        k = max(1, int(round(len(miners) * self.sample_fraction)))
        return rng.sample(list(miners), k)


STRATEGIES: Dict[str, ValidatorStrategy] = {
    "broadcast": ValidatorStrategy(
        key="broadcast", label="Broadcast",
        description="Queries every miner on every task. Highest coverage, "
                    "highest bandwidth cost.",
        sample_fraction=1.0, probe_rate=0.30),
    "sampling": ValidatorStrategy(
        key="sampling", label="Random sampling",
        description="Queries a random 60% subset per task; cheaper and makes "
                    "targeted collusion harder to coordinate.",
        sample_fraction=0.6, probe_rate=0.35),
    "adversarial": ValidatorStrategy(
        key="adversarial", label="Adversarial",
        description="Probes aggressively with mutations to stress robustness.",
        sample_fraction=0.8, probe_rate=0.75),
    "security_focus": ValidatorStrategy(
        key="security_focus", label="Security focus",
        description="Weights code-security verification heavily.",
        category_weights={"code": 0.6, "reasoning": 0.2, "math": 0.1, "data": 0.1},
        sample_fraction=1.0, probe_rate=0.4),
    "quantitative": ValidatorStrategy(
        key="quantitative", label="Quantitative",
        description="Weights math and data-analysis verification heavily.",
        category_weights={"math": 0.45, "data": 0.4, "reasoning": 0.1, "code": 0.05},
        sample_fraction=0.9, probe_rate=0.25),
    "fixed_baseline": ValidatorStrategy(
        key="fixed_baseline", label="Fixed baseline",
        description="Non-adaptive control validator: always difficulty 5. "
                    "Useful for comparing adaptive vs static regimes.",
        sample_fraction=1.0, probe_rate=0.2, adaptivity=0.0, fixed_difficulty=5),
}


def strategy_keys() -> List[str]:
    return list(STRATEGIES)


def get_strategy(key: str) -> ValidatorStrategy:
    if key not in STRATEGIES:
        raise KeyError(f"unknown validator strategy '{key}'")
    return STRATEGIES[key]
