"""Protocol message definitions (validator <-> miner).

IMPORTANT INVARIANT
-------------------
``TaskRequest`` is the ONLY object ever transmitted to a miner. It contains no
ground truth. Ground truth lives in ``subnet.tasks.groundtruth.GroundTruth``
which is held exclusively by the validator process / server side.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Category(str, Enum):
    CODE = "code"
    MATH = "math"
    REASONING = "reasoning"
    DATA = "data"


class VerificationType(str, Enum):
    #: answer must match hidden ground truth exactly (after normalisation)
    EXACT = "exact"
    #: answer is checked by executing a deterministic verifier function
    PROGRAMMATIC = "programmatic"
    #: answer is compared against the weighted agreement of the miner set
    CONSENSUS = "consensus"
    #: answer must survive a semantics-preserving mutation of the task
    ADVERSARIAL = "adversarial"


class TaskStatus(str, Enum):
    GENERATED = "generated"
    DISPATCHED = "dispatched"
    RESPONSES_RECEIVED = "responses_received"
    VERIFIED = "verified"
    SCORED = "scored"
    FAILED = "failed"
    EXPIRED = "expired"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskRequest(BaseModel):
    """Task as seen by a miner. Contains no hidden information."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    category: Category
    difficulty: int = Field(ge=1, le=10)
    prompt: str = Field(min_length=1, max_length=32_000)
    deadline: datetime
    nonce: str = Field(min_length=16, max_length=128)
    verification_type: VerificationType
    #: free-form, miner-visible hints about the expected answer shape
    answer_schema: Dict[str, Any] = Field(default_factory=dict)
    #: set when this task is a mutation/adversarial follow-up of another task
    parent_task_id: Optional[str] = None
    issued_at: datetime = Field(default_factory=_utcnow)
    validator_uid: Optional[int] = None

    def seconds_remaining(self, now: Optional[datetime] = None) -> float:
        now = now or _utcnow()
        return (self.deadline - now).total_seconds()


class Evidence(BaseModel):
    """A single piece of supporting evidence supplied by a miner."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(max_length=64)  # e.g. "step", "citation", "test_case", "trace"
    content: str = Field(max_length=8_000)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class MinerResponse(BaseModel):
    """Response returned by a miner. Server never trusts any score inside."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    miner_uid: int = Field(ge=0)
    #: echo of the task nonce; used for replay protection
    nonce: str = Field(min_length=16, max_length=128)
    answer: str = Field(max_length=16_000)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[Evidence] = Field(default_factory=list, max_length=32)
    reasoning_metadata: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: int = Field(ge=0, le=600_000)
    model_metadata: Dict[str, Any] = Field(default_factory=dict)
    submitted_at: datetime = Field(default_factory=_utcnow)

    @field_validator("answer")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("reasoning_metadata", "model_metadata")
    @classmethod
    def _small_dict(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if len(v) > 32:
            raise ValueError("metadata too large (max 32 keys)")
        return v


class ScoreBreakdown(BaseModel):
    """Transparent per-dimension score. All components in [0, 1]."""

    model_config = ConfigDict(extra="forbid")

    accuracy: float = Field(ge=0.0, le=1.0)
    evidence: float = Field(ge=0.0, le=1.0)
    robustness: float = Field(ge=0.0, le=1.0)
    calibration: float = Field(ge=0.0, le=1.0)
    latency: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    weights: Dict[str, float] = Field(default_factory=dict)
    penalties: Dict[str, float] = Field(default_factory=dict)

    def explain(self) -> List[Dict[str, float]]:
        """Rows for the Score Explorer UI: component x weight = contribution."""
        rows = []
        for name in ("accuracy", "evidence", "robustness", "calibration", "latency"):
            value = getattr(self, name)
            weight = float(self.weights.get(name, 0.0))
            rows.append(
                {"component": name, "value": value, "weight": weight,
                 "contribution": round(value * weight, 6)}
            )
        return rows


class EvaluationResult(BaseModel):
    """Validator's verdict for one (task, miner) pair."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    miner_uid: int
    validator_uid: int
    correct: bool
    correctness_score: float = Field(ge=0.0, le=1.0)
    breakdown: ScoreBreakdown
    robustness_tested: bool = False
    robustness_consistent: Optional[bool] = None
    flags: List[str] = Field(default_factory=list)
    notes: str = ""
    evaluated_at: datetime = Field(default_factory=_utcnow)
