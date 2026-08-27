"""Miner reputation: EMA smoothing, per-category stats and trend history."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

from ..protocol.messages import Category, ScoreBreakdown
from .components import clamp
from .config import DEFAULT_CONFIG, MechanismConfig


@dataclass(slots=True)
class CategoryStats:
    tasks: int = 0
    correct: float = 0.0
    score_sum: float = 0.0

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.tasks, 6) if self.tasks else 0.0

    @property
    def mean_score(self) -> float:
        return round(self.score_sum / self.tasks, 6) if self.tasks else 0.0


@dataclass(slots=True)
class ReputationSnapshot:
    timestamp: datetime
    task_id: str
    score: float
    rolling_score: float
    accuracy: float
    emission_weight: float


class MinerReputation:
    """Reputation state machine for a single miner.

    Key property: *smoothing before trust*. A miner's ``reputation`` is the EMA
    of its task scores, shrunk toward a low prior until it has completed
    ``min_tasks_for_full_trust`` tasks. A single lucky task therefore cannot
    move a fresh miner to the top of the leaderboard — which is exactly the
    attack a naive mean-of-scores mechanism invites.
    """

    def __init__(self, uid: int, name: str,
                 config: MechanismConfig = DEFAULT_CONFIG) -> None:
        self.uid = uid
        self.name = name
        self.config = config
        self.task_count = 0
        self.correct_count = 0.0
        self.lifetime_score_sum = 0.0
        self._ema: Optional[float] = None
        self.confidences: List[float] = []
        self.outcomes: List[float] = []
        self.probe_outcomes: List[bool] = []
        self.latency_samples: Deque[int] = deque(maxlen=200)
        self.category: Dict[str, CategoryStats] = defaultdict(CategoryStats)
        self.history: Deque[ReputationSnapshot] = deque(
            maxlen=config.reputation.history_limit)
        self.emission_weight = 0.0
        self.emission_history: Deque[float] = deque(maxlen=config.reputation.history_limit)
        self.flags: Dict[str, int] = defaultdict(int)
        self.last_components: Dict[str, float] = {}

    # -- updates ----------------------------------------------------------
    def record(self, task_id: str, category: Category, breakdown: ScoreBreakdown,
               confidence: float, latency_ms: int,
               probe_outcome: Optional[bool] = None,
               flags: Optional[List[str]] = None) -> None:
        alpha = self.config.reputation.ema_alpha
        s = clamp(breakdown.final_score)
        # Outlier protection: bound how far a single task may sit from the
        # running EMA before it is folded in. The EMA already damps a single
        # result; this stops a pathological score from moving even α of the way.
        if self._ema is not None:
            delta_cap = self.config.outliers.max_single_task_delta
            s = max(self._ema - delta_cap, min(self._ema + delta_cap, s))
        self.task_count += 1
        self.correct_count += clamp(breakdown.accuracy)
        self.lifetime_score_sum += s
        self._ema = s if self._ema is None else (1 - alpha) * self._ema + alpha * s
        self.confidences.append(clamp(confidence))
        self.outcomes.append(clamp(breakdown.accuracy))
        window = self.config.calibration.window * 4
        if len(self.confidences) > window:
            self.confidences = self.confidences[-window:]
            self.outcomes = self.outcomes[-window:]
        self.latency_samples.append(max(0, int(latency_ms)))
        cs = self.category[category.value]
        cs.tasks += 1
        cs.correct += clamp(breakdown.accuracy)
        cs.score_sum += s
        if probe_outcome is not None:
            self.probe_outcomes.append(bool(probe_outcome))
            self.probe_outcomes = self.probe_outcomes[-100:]
        for f in flags or []:
            self.flags[f] += 1
        self.last_components = {
            "accuracy": breakdown.accuracy, "evidence": breakdown.evidence,
            "robustness": breakdown.robustness, "calibration": breakdown.calibration,
            "latency": breakdown.latency,
        }
        self.history.append(ReputationSnapshot(
            timestamp=datetime.now(timezone.utc), task_id=task_id, score=s,
            rolling_score=self.rolling_score, accuracy=self.accuracy,
            emission_weight=self.emission_weight))

    def set_emission(self, weight: float) -> None:
        self.emission_weight = clamp(weight)
        self.emission_history.append(self.emission_weight)

    # -- derived metrics --------------------------------------------------
    @property
    def rolling_score(self) -> float:
        """EMA of recent task scores (no trust shrinkage applied)."""
        return round(clamp(self._ema if self._ema is not None else 0.0), 6)

    @property
    def lifetime_score(self) -> float:
        return round(self.lifetime_score_sum / self.task_count, 6) if self.task_count else 0.0

    @property
    def reputation(self) -> float:
        """Trust-shrunk rolling score — the value that drives emissions."""
        rp = self.config.reputation
        if self.task_count == 0:
            return 0.0
        trust = min(1.0, self.task_count / max(1, rp.min_tasks_for_full_trust))
        return round(clamp(trust * self.rolling_score + (1 - trust) * rp.prior_score
                           * min(1.0, self.rolling_score / max(rp.prior_score, 1e-9))), 6)

    @property
    def accuracy(self) -> float:
        return round(self.correct_count / self.task_count, 6) if self.task_count else 0.0

    @property
    def mean_latency_ms(self) -> float:
        return round(sum(self.latency_samples) / len(self.latency_samples), 2) \
            if self.latency_samples else 0.0

    @property
    def trend(self) -> float:
        """Difference between the last 10 and previous 10 rolling scores."""
        pts = [h.score for h in self.history]
        if len(pts) < 6:
            return 0.0
        recent = pts[-10:]
        prior = pts[-20:-10] or pts[:-10] or recent
        return round(sum(recent) / len(recent) - sum(prior) / len(prior), 6)

    def snapshot(self) -> Dict[str, object]:
        return {
            "uid": self.uid,
            "name": self.name,
            "reputation": self.reputation,
            "rolling_score": self.rolling_score,
            "lifetime_score": self.lifetime_score,
            "accuracy": self.accuracy,
            "task_count": self.task_count,
            "mean_latency_ms": self.mean_latency_ms,
            "emission_weight": self.emission_weight,
            "trend": self.trend,
            "components": dict(self.last_components),
            "categories": {k: {"tasks": v.tasks, "accuracy": v.accuracy,
                               "mean_score": v.mean_score}
                           for k, v in self.category.items()},
            "flags": dict(self.flags),
        }
