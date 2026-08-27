"""Miner base class shared by simulated and real (model-backed) miners."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..protocol.messages import Evidence, MinerResponse, TaskRequest
from .model import ModelBackend, default_backend


class BaseMiner(ABC):
    """A miner receives a :class:`TaskRequest` and returns a MinerResponse.

    The base class owns the parts that must be identical in simulation and on
    testnet: timing, nonce echo (replay protection), evidence packing and
    schema-valid construction of the response.
    """

    def __init__(self, uid: int, name: str, backend: Optional[ModelBackend] = None) -> None:
        self.uid = uid
        self.name = name
        self.backend = backend or default_backend()

    @abstractmethod
    def _solve(self, task: TaskRequest) -> tuple[str, float, List[str], Dict[str, Any]]:
        """Return ``(answer, confidence, evidence_strings, reasoning_metadata)``."""

    def handle(self, task: TaskRequest) -> Optional[MinerResponse]:
        """Full request handling. Returns ``None`` when the miner drops the task."""
        started = time.perf_counter()
        result = self._solve(task)
        if result is None:
            return None
        answer, confidence, evidence, meta = result
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        declared = int(meta.pop("_simulated_latency_ms", elapsed_ms))
        return MinerResponse(
            task_id=task.task_id,
            miner_uid=self.uid,
            nonce=task.nonce,              # replay protection: echo, never invent
            answer=answer,
            confidence=max(0.0, min(1.0, float(confidence))),
            evidence=[Evidence(kind="reasoning", content=e[:8000],
                               weight=1.0) for e in evidence[:32]],
            reasoning_metadata=meta,
            execution_time_ms=max(0, min(600_000, declared)),
            model_metadata={"backend": getattr(self.backend, "name", "unknown"),
                            "miner": self.name},
        )


class ModelMiner(BaseMiner):
    """Production-shaped miner: delegates entirely to a ModelBackend.

    This is the class a real subnet operator would run (wired to the Bittensor
    axon in ``subnet/adapters/bittensor_adapter.py``).
    """

    def _solve(self, task: TaskRequest):
        out = self.backend.complete(task.prompt, context={
            "category": task.category.value,
            "difficulty": task.difficulty,
            "answer_schema": task.answer_schema,
        })
        confidence = float(out.metadata.get("confidence", 0.5))
        return out.text, confidence, out.evidence, {"source": "model_backend"}
