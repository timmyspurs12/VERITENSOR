"""Miner behaviour profiles for the local simulation.

These profiles exist so the *mechanism* can be evaluated: a scoring engine is
only credible if it visibly separates a hallucinating miner from a calibrated
one. Profiles parameterise error rate, latency, confidence bias, evidence
quality and robustness decay. Nothing in the dashboard is hand-written — every
number the UI shows is produced by running these agents through the real
validator pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..protocol.messages import Category


@dataclass(frozen=True, slots=True)
class MinerProfile:
    key: str
    label: str
    description: str
    #: P(correct) at difficulty 5, per category (default applies when absent)
    accuracy: Dict[str, float] = field(default_factory=dict)
    base_accuracy: float = 0.7
    #: how much each difficulty point above 5 costs in accuracy
    difficulty_penalty: float = 0.045
    #: log-normal-ish latency in ms
    latency_mean_ms: float = 1500.0
    latency_jitter: float = 0.35
    #: additive bias applied to the honest confidence estimate
    confidence_bias: float = 0.0
    #: how tightly stated confidence tracks true correctness probability (0..1)
    confidence_fidelity: float = 0.8
    #: quality of supplied evidence (0..1) -> drives evidence sub-score
    evidence_quality: float = 0.7
    #: extra probability of flipping the answer under mutation
    robustness_decay: float = 0.10
    #: emits near-identical boilerplate answers (duplicate detection bait)
    gaming: bool = False
    #: probability of missing the deadline entirely
    dropout: float = 0.01

    def accuracy_for(self, category: Category, difficulty: int) -> float:
        base = self.accuracy.get(category.value, self.base_accuracy)
        adj = base - self.difficulty_penalty * (difficulty - 5)
        return max(0.02, min(0.995, adj))


PROFILES: Dict[str, MinerProfile] = {
    "high_quality": MinerProfile(
        key="high_quality", label="High-quality",
        description="Deep verification, strong evidence, deliberately slow.",
        base_accuracy=0.92, difficulty_penalty=0.030,
        latency_mean_ms=4200, latency_jitter=0.25,
        confidence_bias=-0.02, confidence_fidelity=0.93,
        evidence_quality=0.92, robustness_decay=0.04, dropout=0.01),
    "fast": MinerProfile(
        key="fast", label="Fast",
        description="Low latency, good but not exceptional accuracy.",
        base_accuracy=0.80, difficulty_penalty=0.055,
        latency_mean_ms=650, latency_jitter=0.30,
        confidence_bias=0.03, confidence_fidelity=0.78,
        evidence_quality=0.55, robustness_decay=0.12, dropout=0.01),
    "balanced": MinerProfile(
        key="balanced", label="Balanced",
        description="Strong all-round performance with moderate latency.",
        base_accuracy=0.86, difficulty_penalty=0.040,
        latency_mean_ms=1800, latency_jitter=0.28,
        confidence_bias=0.0, confidence_fidelity=0.88,
        evidence_quality=0.78, robustness_decay=0.07, dropout=0.01),
    "weak": MinerProfile(
        key="weak", label="Weak",
        description="Under-powered model; frequently wrong on hard items.",
        base_accuracy=0.48, difficulty_penalty=0.060,
        latency_mean_ms=2200, latency_jitter=0.45,
        confidence_bias=-0.05, confidence_fidelity=0.62,
        evidence_quality=0.35, robustness_decay=0.18, dropout=0.04),
    "hallucinating": MinerProfile(
        key="hallucinating", label="Hallucinating",
        description="Answers confidently regardless of correctness. "
                    "Calibration penalty should dominate its score.",
        base_accuracy=0.55, difficulty_penalty=0.055,
        latency_mean_ms=1100, latency_jitter=0.30,
        confidence_bias=0.42, confidence_fidelity=0.05,
        evidence_quality=0.45, robustness_decay=0.22, dropout=0.01),
    "gaming": MinerProfile(
        key="gaming", label="Gaming",
        description="Emits repetitive low-information boilerplate to farm "
                    "emissions. Should be caught by duplicate detection.",
        base_accuracy=0.30, difficulty_penalty=0.020,
        latency_mean_ms=220, latency_jitter=0.15,
        confidence_bias=0.35, confidence_fidelity=0.02,
        evidence_quality=0.08, robustness_decay=0.30, gaming=True, dropout=0.0),
    "specialist_code": MinerProfile(
        key="specialist_code", label="Specialist (code)",
        description="Excellent on code verification, mediocre elsewhere.",
        accuracy={"code": 0.95, "math": 0.55, "reasoning": 0.58, "data": 0.60},
        base_accuracy=0.58, difficulty_penalty=0.045,
        latency_mean_ms=1600, latency_jitter=0.30,
        confidence_bias=0.02, confidence_fidelity=0.82,
        evidence_quality=0.72, robustness_decay=0.09, dropout=0.01),
    "specialist_math": MinerProfile(
        key="specialist_math", label="Specialist (math)",
        description="Excellent on mathematics, weak on code security.",
        accuracy={"math": 0.96, "data": 0.80, "code": 0.45, "reasoning": 0.68},
        base_accuracy=0.62, difficulty_penalty=0.040,
        latency_mean_ms=1400, latency_jitter=0.28,
        confidence_bias=-0.01, confidence_fidelity=0.86,
        evidence_quality=0.70, robustness_decay=0.08, dropout=0.01),
    "unstable": MinerProfile(
        key="unstable", label="Unstable",
        description="Accurate when it answers, but often times out.",
        base_accuracy=0.84, difficulty_penalty=0.045,
        latency_mean_ms=5200, latency_jitter=0.75,
        confidence_bias=0.0, confidence_fidelity=0.80,
        evidence_quality=0.66, robustness_decay=0.10, dropout=0.14),
}


def profile_keys() -> List[str]:
    return list(PROFILES)


def get_profile(key: str) -> MinerProfile:
    if key not in PROFILES:
        raise KeyError(f"unknown miner profile '{key}'")
    return PROFILES[key]
