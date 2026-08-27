"""Records produced by the validator, consumed by storage and the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..protocol.messages import (Category, EvaluationResult, MinerResponse,
                                 TaskStatus, VerificationType)


@dataclass(slots=True)
class ResponseRecord:
    miner_uid: int
    miner_name: str
    answer: str
    confidence: float
    execution_time_ms: int
    evidence: List[str]
    correct: bool
    accuracy: float
    score: float
    breakdown: Dict[str, float]
    penalties: Dict[str, float]
    flags: List[str]
    rejected: bool = False
    rejection_reason: str = ""
    probe: Optional[Dict[str, Any]] = None
    model_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    category: Category
    difficulty: int
    prompt: str
    verification_type: VerificationType
    validator_uid: int
    validator_name: str
    generator: str
    status: TaskStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    kind: str = "generated"          # generated | mutation | benchmark | adversarial
    parent_task_id: Optional[str] = None
    responses: List[ResponseRecord] = field(default_factory=list)
    consensus: Dict[str, float] = field(default_factory=dict)
    #: revealed only once the task is closed; never sent to miners
    ground_truth: Optional[str] = None
    ground_truth_explanation: str = ""
    commitment: str = ""
    dropped_miners: List[int] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        if not self.completed_at:
            return 0
        return int((self.completed_at - self.created_at).total_seconds() * 1000)

    def public_dict(self, reveal_truth: bool = False) -> Dict[str, Any]:
        """Serialisation used by the API. ``reveal_truth`` is only ever set for
        CLOSED tasks by an explicitly authorised endpoint."""
        data: Dict[str, Any] = {
            "task_id": self.task_id,
            "category": self.category.value,
            "difficulty": self.difficulty,
            "prompt": self.prompt,
            "verification_type": self.verification_type.value,
            "validator_uid": self.validator_uid,
            "validator_name": self.validator_name,
            "generator": self.generator,
            "status": self.status.value,
            "kind": self.kind,
            "parent_task_id": self.parent_task_id,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "consensus": self.consensus,
            "commitment": self.commitment,
            "dropped_miners": self.dropped_miners,
            "response_count": len(self.responses),
            "responses": [
                {
                    "miner_uid": r.miner_uid, "miner_name": r.miner_name,
                    "answer": r.answer, "confidence": r.confidence,
                    "execution_time_ms": r.execution_time_ms,
                    "evidence": r.evidence, "correct": r.correct,
                    "accuracy": r.accuracy, "score": r.score,
                    "breakdown": r.breakdown, "penalties": r.penalties,
                    "flags": r.flags, "rejected": r.rejected,
                    "rejection_reason": r.rejection_reason, "probe": r.probe,
                    "model_metadata": r.model_metadata,
                }
                for r in self.responses
            ],
            "ground_truth_available": self.ground_truth is not None,
        }
        if reveal_truth and self.status in (TaskStatus.SCORED, TaskStatus.VERIFIED):
            data["ground_truth"] = self.ground_truth
            data["ground_truth_explanation"] = self.ground_truth_explanation
        return data
