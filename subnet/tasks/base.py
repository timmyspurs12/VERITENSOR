"""Task engine core types.

A generator produces a :class:`GeneratedTask` = (public ``TaskRequest``,
private :class:`GroundTruth`). The public half is the only thing that may
leave the validator boundary.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Protocol

from ..protocol.messages import Category, TaskRequest, VerificationType, _utcnow
from ..protocol.signing import new_nonce, new_task_id


@dataclass(slots=True)
class GroundTruth:
    """Hidden answer + everything needed to grade a response.

    NEVER serialise this to a miner-facing or public API response. The API
    layer enforces this via dedicated response schemas (see
    ``backend/schemas/task.py``) and a regression test
    (``tests/test_api_security.py::test_ground_truth_never_leaks``).
    """

    answer: str
    #: name of the registered verifier used to grade a free-form answer
    verifier: str = "exact"
    #: extra parameters handed to the verifier (tolerance, accepted aliases...)
    params: Dict[str, Any] = field(default_factory=dict)
    #: tokens that a *good* explanation is expected to mention (evidence score)
    evidence_keywords: List[str] = field(default_factory=list)
    #: human readable rationale, shown only after a task is closed
    explanation: str = ""
    #: seed used to generate the task, enables exact reproduction
    seed: int = 0


@dataclass(slots=True)
class GeneratedTask:
    request: TaskRequest
    ground_truth: GroundTruth
    #: opaque generator state used by the mutation engine to build variants
    mutation_spec: Dict[str, Any] = field(default_factory=dict)
    generator: str = ""

    @property
    def task_id(self) -> str:
        return self.request.task_id


class TaskGenerator(Protocol):
    """Protocol implemented by every generator."""

    name: str
    category: Category

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask: ...


_REGISTRY: Dict[str, "BaseGenerator"] = {}


def register(gen):
    """Register a generator. Usable as a class decorator or with an instance."""
    instance = gen() if isinstance(gen, type) else gen
    _REGISTRY[instance.name] = instance
    return gen


def registry() -> Dict[str, "BaseGenerator"]:
    return dict(_REGISTRY)


def generators_for(category: Category) -> List["BaseGenerator"]:
    return [g for g in _REGISTRY.values() if g.category == category]


class BaseGenerator:
    """Convenience base class handling ids, nonces and deadlines."""

    name: str = "base"
    category: Category = Category.MATH
    verification_type: VerificationType = VerificationType.EXACT
    default_timeout_s: int = 30

    def build_request(
        self,
        prompt: str,
        difficulty: int,
        *,
        answer_schema: Optional[Dict[str, Any]] = None,
        verification_type: Optional[VerificationType] = None,
        parent_task_id: Optional[str] = None,
        validator_uid: Optional[int] = None,
        timeout_s: Optional[int] = None,
    ) -> TaskRequest:
        return TaskRequest(
            task_id=new_task_id(),
            category=self.category,
            difficulty=max(1, min(10, int(difficulty))),
            prompt=prompt,
            deadline=_utcnow() + timedelta(seconds=timeout_s or self.default_timeout_s),
            nonce=new_nonce(),
            verification_type=verification_type or self.verification_type,
            answer_schema=answer_schema or {},
            parent_task_id=parent_task_id,
            validator_uid=validator_uid,
        )

    # ---- to be implemented by subclasses -------------------------------
    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:  # pragma: no cover
        raise NotImplementedError

    def mutate(
        self, task: GeneratedTask, rng: random.Random
    ) -> Optional[GeneratedTask]:
        """Return a semantics-preserving variant, or ``None`` if unsupported.

        The mutated task MUST have the same ground-truth answer as the parent;
        that is exactly what makes it a robustness probe.
        """
        return None
