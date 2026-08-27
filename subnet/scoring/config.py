"""Central configuration for the incentive mechanism.

Every tunable of the mechanism lives here. Nothing in the scoring, reputation
or emission code hardcodes a weight or a threshold: the config object is
threaded through, which is what makes the mechanism auditable and what allows
the UI to render the exact weights that produced a score.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict


@dataclass(frozen=True, slots=True)
class ScoreWeights:
    accuracy: float = 0.45
    evidence: float = 0.20
    robustness: float = 0.15
    calibration: float = 0.10
    latency: float = 0.10

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)

    def validate(self) -> None:
        total = sum(self.as_dict().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"score weights must sum to 1.0, got {total}")
        if any(v < 0 for v in self.as_dict().values()):
            raise ValueError("score weights must be non-negative")


@dataclass(frozen=True, slots=True)
class OutlierPolicy:
    """Protection against single anomalous observations.

    A neuron can report an absurd execution time (clock skew, a stalled GPU, or
    a deliberate lie), and a response can be structurally valid yet semantically
    empty. Neither should be able to swing a component score, so:

    * reported latency is winsorised at ``latency_clamp_ms`` before scoring;
    * an answer that is only whitespace/punctuation, or longer than
      ``max_answer_chars``, scores zero on accuracy and evidence rather than
      being fed to a verifier;
    * a per-task score is capped at ``max_single_task_delta`` distance from the
      miner's current EMA before it enters reputation, so one outlier task
      cannot dominate (belt and braces on top of the EMA itself).
    """

    latency_clamp_ms: int = 120_000
    max_answer_chars: int = 16_000
    min_meaningful_chars: int = 1
    max_single_task_delta: float = 0.5


@dataclass(frozen=True, slots=True)
class LatencyPolicy:
    """Latency is scored against a budget, not against the fastest miner.

    Rewarding relative speed invites a race to the bottom (answer instantly,
    be wrong). A budget keeps latency a *hygiene* factor: full marks under
    ``target_ms``, decaying to zero at ``timeout_ms``.
    """

    target_ms: int = 1200
    timeout_ms: int = 15_000
    #: floor so that a slow-but-correct miner is not zeroed out
    floor: float = 0.05


@dataclass(frozen=True, slots=True)
class CalibrationPolicy:
    """Brier-score based calibration.

    brier = mean((confidence - outcome)^2) over the miner's recent window.
    A perfectly calibrated & confident miner tends to 0; always-0.95-confident
    but 60% correct gives brier ~ 0.29 -> calibration score ~ 0.42.
    """

    window: int = 50
    #: brier at/above this maps to 0 (0.25 == "always said 0.5", i.e. useless)
    worst_brier: float = 0.25
    min_samples: int = 5
    #: score used before enough samples exist (neutral prior)
    prior: float = 0.5


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    """Evidence quality: coverage of expected concepts + structure + brevity."""

    keyword_weight: float = 0.55
    structure_weight: float = 0.25
    specificity_weight: float = 0.20
    min_chars: int = 24
    max_useful_items: int = 5
    #: answers with no evidence at all still get this (they can be correct)
    empty_score: float = 0.0


@dataclass(frozen=True, slots=True)
class RobustnessPolicy:
    """Robustness = consistency across semantics-preserving mutations."""

    #: probability a validator issues a mutation probe after a correct answer
    probe_rate: float = 0.35
    #: score assigned before any probe has been run (neutral, not free marks)
    prior: float = 0.5
    #: EMA alpha over probe outcomes
    alpha: float = 0.3


@dataclass(frozen=True, slots=True)
class ReputationPolicy:
    """Temporal smoothing so one lucky task cannot dominate reputation."""

    ema_alpha: float = 0.15
    #: below this many scored tasks reputation is shrunk toward the prior
    min_tasks_for_full_trust: int = 20
    prior_score: float = 0.35
    history_limit: int = 500


@dataclass(frozen=True, slots=True)
class PenaltyPolicy:
    duplicate_response: float = 0.45      # identical answer text across tasks
    boilerplate_evidence: float = 0.20    # low-information evidence reuse
    schema_violation: float = 0.50
    replay_attempt: float = 1.00          # zeroes the score for that task
    deadline_miss: float = 0.30
    #: max cumulative penalty applied to one task score
    cap: float = 1.0


@dataclass(frozen=True, slots=True)
class EmissionPolicy:
    """Score -> emission weight transformation."""

    #: exponent sharpening the distribution (1 = proportional, >1 = winner-lean)
    temperature: float = 2.5
    #: miners below this reputation receive zero emission
    floor_score: float = 0.25
    #: no single miner may exceed this share (relaxed to 2/n in tiny networks)
    max_share: float = 0.25
    #: minimum scored tasks before a miner is emission-eligible
    min_tasks: int = 10
    #: share reserved and burned when eligible weight is missing (kept explicit)
    burn_unallocated: bool = False


@dataclass(frozen=True, slots=True)
class DifficultyPolicy:
    """Adaptive difficulty thresholds (configurable, see docs/MECHANISM.md)."""

    easy_below: float = 0.60
    normal_below: float = 0.80
    hard_below: float = 0.90
    easy_range: tuple[int, int] = (1, 3)
    normal_range: tuple[int, int] = (4, 6)
    hard_range: tuple[int, int] = (7, 8)
    adversarial_range: tuple[int, int] = (9, 10)


@dataclass(frozen=True, slots=True)
class MechanismConfig:
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    latency: LatencyPolicy = field(default_factory=LatencyPolicy)
    calibration: CalibrationPolicy = field(default_factory=CalibrationPolicy)
    evidence: EvidencePolicy = field(default_factory=EvidencePolicy)
    robustness: RobustnessPolicy = field(default_factory=RobustnessPolicy)
    reputation: ReputationPolicy = field(default_factory=ReputationPolicy)
    outliers: OutlierPolicy = field(default_factory=OutlierPolicy)
    penalties: PenaltyPolicy = field(default_factory=PenaltyPolicy)
    emission: EmissionPolicy = field(default_factory=EmissionPolicy)
    difficulty: DifficultyPolicy = field(default_factory=DifficultyPolicy)

    def __post_init__(self) -> None:
        self.weights.validate()

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, default=str)

    def as_dict(self) -> dict:
        return {
            "weights": self.weights.as_dict(),
            "latency": asdict(self.latency),
            "calibration": asdict(self.calibration),
            "evidence": asdict(self.evidence),
            "robustness": asdict(self.robustness),
            "reputation": asdict(self.reputation),
            "outliers": asdict(self.outliers),
            "penalties": asdict(self.penalties),
            "emission": asdict(self.emission),
            "difficulty": asdict(self.difficulty),
        }


def default_config() -> MechanismConfig:
    """Config with optional environment overrides for the score weights."""
    raw = os.getenv("VERITENSOR_SCORE_WEIGHTS")
    if not raw:
        return MechanismConfig()
    try:
        data = json.loads(raw)
        return MechanismConfig(weights=ScoreWeights(**data))
    except Exception as exc:  # pragma: no cover - operator error path
        raise ValueError(f"invalid VERITENSOR_SCORE_WEIGHTS: {exc}") from exc


DEFAULT_CONFIG = default_config()
