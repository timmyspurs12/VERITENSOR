"""Scoring, reputation, emissions and anti-gaming."""

from .antigaming import AntiGamingGuard, GuardReport, RateLimitRule
from .components import (accuracy_score, brier_score, calibration_score, clamp,
                         evidence_score, latency_score, robustness_score)
from .config import (DEFAULT_CONFIG, MechanismConfig, ScoreWeights,
                     default_config)
from .emissions import (EmissionInput, EmissionResult, compute_emissions,
                        weights_to_bittensor)
from .engine import ScoringContext, ScoringEngine, aggregate_scores
from .reputation import MinerReputation, ReputationSnapshot

__all__ = [
    "AntiGamingGuard", "GuardReport", "RateLimitRule", "MechanismConfig",
    "ScoreWeights", "DEFAULT_CONFIG", "default_config", "ScoringEngine",
    "ScoringContext", "aggregate_scores", "MinerReputation", "ReputationSnapshot",
    "compute_emissions", "EmissionInput", "EmissionResult", "weights_to_bittensor",
    "accuracy_score", "evidence_score", "robustness_score", "calibration_score",
    "latency_score", "brier_score", "clamp",
]
