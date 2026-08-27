"""Schemas for subnet resources.

Note the deliberate omission: no schema in this module contains a
``ground_truth`` field except :class:`GroundTruthReveal`, which is only used by
the authenticated admin route for CLOSED tasks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------- requests
class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    miners: int = Field(default=10, ge=1, le=60)
    validators: int = Field(default=3, ge=1, le=7)
    tasks: int = Field(default=50, ge=1, le=400)
    difficulty: str = Field(default="adaptive")
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    fresh_network: bool = True

    @field_validator("difficulty")
    @classmethod
    def _difficulty(cls, v: str) -> str:
        allowed = {"easy", "normal", "hard", "adaptive"}
        if v not in allowed:
            raise ValueError(f"difficulty must be one of {sorted(allowed)}")
        return v


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Optional[str] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=10)
    validator_uid: Optional[int] = Field(default=None, ge=0)

    @field_validator("category")
    @classmethod
    def _category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"code", "math", "reasoning", "data"}
        if v not in allowed:
            raise ValueError(f"category must be one of {sorted(allowed)}")
        return v


class RegisterMinerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str = Field(default="balanced")
    name: Optional[str] = Field(default=None, max_length=48, pattern=r"^[\w\- ]+$")


class MinerResponseSubmission(BaseModel):
    """Miner-submitted answer.

    SECURITY: the client may not supply accuracy, score, reputation or emission
    values — those fields do not exist here and are computed server-side.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=3, max_length=64)
    miner_uid: int = Field(ge=0)
    nonce: str = Field(min_length=16, max_length=128)
    answer: str = Field(min_length=1, max_length=16_000)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list, max_length=32)
    execution_time_ms: int = Field(ge=0, le=600_000)
    model_metadata: Dict[str, Any] = Field(default_factory=dict)


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=3, max_length=64)
    validator_uid: Optional[int] = Field(default=None, ge=0)


# --------------------------------------------------------------- responses
class NetworkStatsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: str
    netuid: int
    active_miners: int
    active_validators: int
    tasks_verified: int
    network_accuracy: float
    mean_latency_ms: float
    throughput_per_min: float


class MinerSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    uid: int
    name: str
    rank: Optional[int] = None
    reputation: float
    accuracy: float
    task_count: int
    emission_weight: float


class TaskSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    category: str
    difficulty: int
    status: str
    validator_name: str


class GroundTruthReveal(BaseModel):
    task_id: str
    ground_truth: Optional[str]
    explanation: str = ""
    commitment: str = ""
