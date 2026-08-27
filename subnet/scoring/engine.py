"""Scoring engine: combines components into a transparent final score."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..protocol.messages import MinerResponse, ScoreBreakdown
from ..tasks.base import GroundTruth
from .components import (accuracy_score, calibration_score, clamp,
                         evidence_score, is_junk_answer, latency_score,
                         robustness_score, winsorise_latency)
from .config import DEFAULT_CONFIG, MechanismConfig


@dataclass(slots=True)
class ScoringContext:
    """Per-miner history the engine needs beyond the single response."""

    confidences: List[float] = field(default_factory=list)
    outcomes: List[float] = field(default_factory=list)
    probe_outcomes: List[bool] = field(default_factory=list)
    robustness_prior: Optional[float] = None
    penalties: Dict[str, float] = field(default_factory=dict)


class ScoringEngine:
    """Deterministic, configuration-driven scorer.

    ``score()`` never trusts anything a miner asserts about its own quality:
    the only miner-supplied inputs are the answer text, the confidence value
    (which is *graded*, not believed) and the evidence body.
    """

    def __init__(self, config: MechanismConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def score(self, response: MinerResponse, ground_truth: GroundTruth,
              context: Optional[ScoringContext] = None) -> ScoreBreakdown:
        cfg = self.config
        ctx = context or ScoringContext()

        acc = accuracy_score(response.answer, ground_truth, cfg.outliers)
        ev = evidence_score(response.evidence, ground_truth, cfg.evidence,
                            cfg.outliers)
        rob = robustness_score(ctx.probe_outcomes, cfg.robustness,
                               ctx.robustness_prior)
        cal = calibration_score(
            list(ctx.confidences) + [response.confidence],
            list(ctx.outcomes) + [acc],
            cfg.calibration,
        )
        lat = latency_score(winsorise_latency(response.execution_time_ms,
                                              cfg.outliers), cfg.latency)

        w = cfg.weights
        raw = (acc * w.accuracy + ev * w.evidence + rob * w.robustness
               + cal * w.calibration + lat * w.latency)

        penalty_total = min(cfg.penalties.cap, sum(max(0.0, v)
                                                   for v in ctx.penalties.values()))
        final = clamp(raw * (1.0 - penalty_total))

        return ScoreBreakdown(
            accuracy=acc, evidence=ev, robustness=rob, calibration=cal,
            latency=lat, final_score=final, weights=w.as_dict(),
            penalties={k: round(v, 6) for k, v in ctx.penalties.items()},
        )

    def explain(self, breakdown: ScoreBreakdown) -> Dict[str, object]:
        """Structured explanation used by the Score Explorer UI."""
        rows = breakdown.explain()
        subtotal = sum(r["contribution"] for r in rows)
        penalty = sum(breakdown.penalties.values())
        return {
            "rows": rows,
            "subtotal": round(subtotal, 6),
            "penalty_total": round(min(self.config.penalties.cap, penalty), 6),
            "final_score": breakdown.final_score,
            "formula": ("final = (accuracy*w_a + evidence*w_e + robustness*w_r + "
                        "calibration*w_c + latency*w_l) * (1 - penalties)"),
        }


def aggregate_scores(scores: Sequence[float]) -> float:
    """Safe mean used across the codebase (empty -> 0.0, NaN-proof)."""
    vals = [clamp(s) for s in scores]
    return round(sum(vals) / len(vals), 6) if vals else 0.0
