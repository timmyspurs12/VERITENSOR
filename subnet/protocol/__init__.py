"""VERITENSOR subnet protocol.

Defines the wire format between validators and miners. This module is
deliberately dependency-light (pydantic only) so that it can be imported by
the miner process, the validator process, the FastAPI backend and by a future
Bittensor synapse wrapper without pulling in the whole application.
"""

from .messages import (
    Category,
    VerificationType,
    TaskRequest,
    MinerResponse,
    Evidence,
    ScoreBreakdown,
    EvaluationResult,
    TaskStatus,
)
from .signing import new_nonce, new_task_id, task_commitment, verify_commitment

__all__ = [
    "Category",
    "VerificationType",
    "TaskRequest",
    "MinerResponse",
    "Evidence",
    "ScoreBreakdown",
    "EvaluationResult",
    "TaskStatus",
    "new_nonce",
    "new_task_id",
    "task_commitment",
    "verify_commitment",
]
