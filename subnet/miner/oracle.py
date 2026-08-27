"""SIMULATION-ONLY answer oracle.

A simulated miner must be able to be *right on purpose* with probability p, so
the harness injects this oracle. It is a property of the simulation harness,
not of the protocol: the oracle is never reachable from the validator, the API
or a real miner deployment. In a testnet deployment the miner replaces the
oracle with a real :class:`~subnet.miner.model.ModelBackend`.

Keeping it in one small file makes the trust boundary auditable: grep for
``AnswerOracle`` and you can see every place simulation-only knowledge is used.
"""

from __future__ import annotations

import random
import re
from typing import List

from ..tasks.base import GroundTruth


class AnswerOracle:
    """Produces a correct answer, or a *plausible* wrong one, for a task."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def correct(self, gt: GroundTruth) -> str:
        return gt.answer

    def wrong(self, gt: GroundTruth) -> str:
        """A wrong answer that still has the right *shape* (harder to filter)."""
        v, a = gt.verifier, gt.answer
        if v == "boolean":
            truthy = {"vulnerable", "yes", "true", "buggy", "correct"}
            return "safe" if a.lower() in truthy else "vulnerable"
        if v == "numeric":
            try:
                val = float(a)
            except ValueError:
                return "0"
            delta = max(1.0, abs(val) * self._rng.uniform(0.05, 0.4))
            out = val + self._rng.choice([-1, 1]) * delta
            return str(int(out)) if float(a).is_integer() else f"{out:.4f}"
        if v == "set_match":
            items: List[str] = list(gt.params.get("items", []))
            pool = [f"n{i:02d}" for i in range(1, 40)]
            noise = self._rng.sample([p for p in pool if p not in items],
                                     k=min(2, max(1, len(items))))
            keep = items[:-1] if len(items) > 1 and self._rng.random() < 0.5 else []
            return ", ".join(keep + noise)
        if v == "sequence":
            items = list(gt.params.get("items", []))
            if len(items) > 1:
                i, j = self._rng.sample(range(len(items)), 2)
                items[i], items[j] = items[j], items[i]
            return ", ".join(items)
        if v == "multiple_choice":
            options = [c for c in "abcd" if c != a.lower()]
            return self._rng.choice(options)
        # exact / fallback: perturb the token
        alt = {"positive": "negative", "negative": "none", "none": "positive"}
        if a.lower() in alt:
            return alt[a.lower()]
        m = re.match(r"^(.*?)(\d+)$", a)
        if m:
            return f"{m.group(1)}{int(m.group(2)) % 5 + 1}"
        return a[::-1] if len(a) > 3 else "unknown"
