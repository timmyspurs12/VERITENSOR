"""Individual score components. Each returns a float in [0, 1].

Pure functions: identical inputs always produce identical outputs, and none of
them can return NaN/inf (guarded by :func:`clamp`).
"""

from __future__ import annotations

import math
import re
from typing import Iterable, List, Optional, Sequence

from ..protocol.messages import Evidence
from ..tasks.base import GroundTruth
from ..tasks.verifiers import verify
from .config import (CalibrationPolicy, EvidencePolicy, LatencyPolicy,
                     OutlierPolicy, RobustnessPolicy)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp to [lo, hi], mapping NaN/inf to ``lo`` (never propagate garbage)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return lo
    if math.isnan(v) or math.isinf(v):
        return lo
    return max(lo, min(hi, v))


# --------------------------------------------------------------------------
# outlier protection
# --------------------------------------------------------------------------
_PUNCT_ONLY = re.compile(r"^[\W_]+$")


def is_junk_answer(answer: str, policy: OutlierPolicy) -> bool:
    """Structurally valid but semantically empty responses.

    Pydantic already bounds the field; this catches the payloads that pass the
    schema and would otherwise reach a verifier: whitespace, punctuation runs,
    and oversized blobs.
    """
    if answer is None:
        return True
    stripped = answer.strip()
    if len(stripped) < policy.min_meaningful_chars:
        return True
    if len(answer) > policy.max_answer_chars:
        return True
    return bool(_PUNCT_ONLY.match(stripped))


def winsorise_latency(execution_time_ms: int, policy: OutlierPolicy) -> int:
    """Clamp a reported latency into a sane range before it is scored."""
    try:
        value = int(execution_time_ms)
    except (TypeError, ValueError):
        return policy.latency_clamp_ms
    return max(0, min(value, policy.latency_clamp_ms))


# --------------------------------------------------------------------------
# accuracy
# --------------------------------------------------------------------------
def accuracy_score(answer: str, ground_truth: GroundTruth,
                   outliers: Optional[OutlierPolicy] = None) -> float:
    """Correctness against hidden ground truth via the registered verifier."""
    if outliers is not None and is_junk_answer(answer, outliers):
        return 0.0
    return clamp(verify(answer, ground_truth))


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------
_BOILERPLATE_MARKERS = (
    "comprehensive multi-step analysis", "as an ai", "standard practice",
    "it depends", "based on the above",
)


def evidence_score(evidence: Sequence[Evidence], ground_truth: GroundTruth,
                   policy: EvidencePolicy,
                   outliers: Optional[OutlierPolicy] = None) -> float:
    """Coverage of expected concepts + structural quality + specificity.

    Deliberately *not* a model-judged score: an LLM judge would be gameable and
    non-deterministic. Concept coverage uses the generator-declared keywords,
    which miners never see.
    """
    if not evidence:
        return clamp(policy.empty_score)
    text = " ".join(e.content for e in evidence).lower()
    if outliers is not None and is_junk_answer(text, outliers):
        return clamp(policy.empty_score)
    if len(text) < policy.min_chars:
        return clamp(0.05)
    if any(m in text for m in _BOILERPLATE_MARKERS):
        return clamp(0.05)

    keywords = [k.lower() for k in ground_truth.evidence_keywords]
    if keywords:
        hits = sum(1 for k in keywords if k in text)
        coverage = hits / len(keywords)
    else:
        coverage = 0.5  # nothing declared: neutral

    items = min(len(evidence), policy.max_useful_items)
    structure = items / policy.max_useful_items

    tokens = re.findall(r"[a-z0-9_\.\-]+", text)
    unique_ratio = len(set(tokens)) / max(1, len(tokens))
    has_numbers = bool(re.search(r"\d", text))
    specificity = clamp(0.6 * unique_ratio + (0.4 if has_numbers else 0.15))

    return clamp(policy.keyword_weight * coverage
                 + policy.structure_weight * structure
                 + policy.specificity_weight * specificity)


# --------------------------------------------------------------------------
# robustness
# --------------------------------------------------------------------------
def robustness_score(probe_outcomes: Sequence[bool], policy: RobustnessPolicy,
                     prior: float | None = None) -> float:
    """EMA over mutation-probe outcomes (True = conclusion held under mutation)."""
    if not probe_outcomes:
        return clamp(policy.prior if prior is None else prior)
    value = policy.prior if prior is None else clamp(prior)
    for outcome in probe_outcomes:
        value = (1 - policy.alpha) * value + policy.alpha * (1.0 if outcome else 0.0)
    return clamp(value)


# --------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------
def brier_score(confidences: Sequence[float], outcomes: Sequence[float]) -> float:
    """Mean squared error between stated confidence and realised correctness."""
    pairs = [(clamp(c), clamp(o)) for c, o in zip(confidences, outcomes)]
    if not pairs:
        return 0.25
    return sum((c - o) ** 2 for c, o in pairs) / len(pairs)


def calibration_score(confidences: Sequence[float], outcomes: Sequence[float],
                      policy: CalibrationPolicy) -> float:
    """Normalise the Brier score into [0, 1].

        calibration = 1 - min(brier, worst_brier) / worst_brier

    Worked example (documented in docs/MECHANISM.md):
    a miner that always reports 0.95 but is correct 60% of the time has
    brier = 0.6*(0.05^2) + 0.4*(0.95^2) = 0.3625 -> calibration = 0.0.
    A miner reporting 0.60 with 60% accuracy has brier = 0.24 -> 0.04...
    hence honest *and discriminative* confidence is what pays: reporting 0.9
    when right and 0.2 when unsure yields brier ~0.05 -> 0.80.
    """
    window = policy.window
    conf = list(confidences)[-window:]
    outs = list(outcomes)[-window:]
    if len(conf) < policy.min_samples:
        return clamp(policy.prior)
    b = brier_score(conf, outs)
    return clamp(1.0 - min(b, policy.worst_brier) / policy.worst_brier)


# --------------------------------------------------------------------------
# latency
# --------------------------------------------------------------------------
def latency_score(execution_time_ms: int, policy: LatencyPolicy) -> float:
    """Full marks under the target budget, linear decay to the timeout."""
    t = max(0, int(execution_time_ms))
    if t <= policy.target_ms:
        return 1.0
    if t >= policy.timeout_ms:
        return clamp(policy.floor)
    span = policy.timeout_ms - policy.target_ms
    decayed = 1.0 - (t - policy.target_ms) / span
    return clamp(max(policy.floor, decayed))


__all__ = ["clamp", "accuracy_score", "evidence_score", "robustness_score",
           "brier_score", "calibration_score", "latency_score",
           "is_junk_answer", "winsorise_latency"]
