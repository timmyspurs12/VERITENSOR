"""Simulated miner: a profile-driven agent used by the local network sim."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from ..protocol.messages import Category, MinerResponse, TaskRequest
from ..tasks.base import GroundTruth
from .base import BaseMiner
from .oracle import AnswerOracle
from .profiles import MinerProfile

_GAMING_BOILERPLATE = (
    "Based on a comprehensive multi-step analysis of the provided material, "
    "the most probable answer is determined to be consistent with standard practice."
)

_EVIDENCE_TEMPLATES = [
    "Identified the governing constraint: {kw}.",
    "Checked {kw} against the stated conditions.",
    "Derived the intermediate result using {kw}.",
    "Cross-validated the conclusion by re-deriving via {kw}.",
    "Ruled out the alternative branch because {kw} does not hold.",
]


class SimulatedMiner(BaseMiner):
    """Behaviour-parameterised miner.

    The miner only ever *sees* a ``TaskRequest``. The harness separately hands
    it the hidden ground truth through :meth:`prime`, which stands in for "the
    model computed something". Whether it then emits the correct answer is
    decided by the profile's accuracy curve — never by peeking at grading.
    """

    def __init__(self, uid: int, name: str, profile: MinerProfile,
                 seed: Optional[int] = None) -> None:
        super().__init__(uid=uid, name=name)
        self.profile = profile
        self._rng = random.Random(seed if seed is not None else uid * 7919)
        self._oracle = AnswerOracle(self._rng)
        self._primed: Dict[str, GroundTruth] = {}
        #: answers already emitted for parent tasks, to model robustness decay
        self._memory: Dict[str, bool] = {}

    # -- harness hooks ----------------------------------------------------
    def prime(self, task: TaskRequest, ground_truth: GroundTruth) -> None:
        """Simulation-only: give the agent the material it would compute itself."""
        self._primed[task.task_id] = ground_truth

    def forget(self, task_id: str) -> None:
        self._primed.pop(task_id, None)

    @property
    def backend_name(self) -> str:
        return f"veritensor-sim/{self.profile.key}"

    # -- miner logic ------------------------------------------------------
    def _solve(self, task: TaskRequest) -> Optional[
        Tuple[str, float, List[str], Dict[str, Any]]
    ]:
        p = self.profile
        gt = self._primed.get(task.task_id)
        if gt is None:  # no model result: honest abstention
            return "unknown", 0.05, ["no result computed"], {"abstained": True}

        if self._rng.random() < p.dropout:
            return None  # dropped / timed out

        p_correct = p.accuracy_for(task.category, task.difficulty)

        # robustness: on a mutated follow-up the miner may flip its conclusion
        if task.parent_task_id is not None:
            parent_correct = self._memory.get(task.parent_task_id)
            if parent_correct is True:
                p_correct = max(0.0, p_correct * (1.0 - p.robustness_decay))
            elif parent_correct is False:
                p_correct = p_correct * 0.6

        correct = self._rng.random() < p_correct
        if p.gaming:
            # gaming miners emit the same boilerplate regardless of the task
            answer = self._gaming_answer(gt)
            correct = answer.strip().lower() == gt.answer.strip().lower()
        else:
            answer = self._oracle.correct(gt) if correct else self._oracle.wrong(gt)

        self._memory[task.task_id] = correct

        confidence = self._confidence(p_correct, correct)
        evidence = self._evidence(gt, correct)
        latency = self._latency(task)
        meta: Dict[str, Any] = {
            "profile": p.key,
            "steps": len(evidence),
            "self_check": bool(not p.gaming and self._rng.random() < p.evidence_quality),
            "_simulated_latency_ms": latency,
        }
        return answer, confidence, evidence, meta

    def _gaming_answer(self, gt: GroundTruth) -> str:
        """Repetitive, low-information output; occasionally right by luck."""
        canned = {
            "boolean": "vulnerable",
            "numeric": "42",
            "exact": "none",
            "set_match": "n01",
            "sequence": "Alpha, Bravo, Cirrus, Delta",
            "multiple_choice": "a",
        }
        return canned.get(gt.verifier, _GAMING_BOILERPLATE)

    # -- components -------------------------------------------------------
    def _confidence(self, p_correct: float, correct: bool) -> float:
        p = self.profile
        honest = p_correct if p.confidence_fidelity > 0 else 0.5
        # fidelity blends the honest estimate with an uninformative 0.9 prior
        blended = (p.confidence_fidelity * honest
                   + (1 - p.confidence_fidelity) * 0.9)
        noise = self._rng.gauss(0, 0.05)
        return max(0.01, min(0.99, blended + p.confidence_bias + noise))

    def _evidence(self, gt: GroundTruth, correct: bool) -> List[str]:
        p = self.profile
        if p.gaming:
            return [_GAMING_BOILERPLATE]
        n = 1 + int(round(p.evidence_quality * 3))
        kws = gt.evidence_keywords or ["the stated constraints"]
        out = []
        for i in range(n):
            kw = kws[i % len(kws)]
            if not correct and self._rng.random() < 0.5:
                kw = f"an assumed simplification of {kw}"
            out.append(self._rng.choice(_EVIDENCE_TEMPLATES).format(kw=kw))
        return out

    def _latency(self, task: TaskRequest) -> int:
        p = self.profile
        scale = 0.8 + 0.06 * task.difficulty
        jitter = max(0.15, self._rng.lognormvariate(0.0, p.latency_jitter))
        return int(max(40, p.latency_mean_ms * scale * jitter))

    # convenience for the harness
    def respond(self, task: TaskRequest, ground_truth: GroundTruth
                ) -> Optional[MinerResponse]:
        self.prime(task, ground_truth)
        try:
            return self.handle(task)
        finally:
            self.forget(task.task_id)
