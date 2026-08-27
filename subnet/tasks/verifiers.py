"""Deterministic answer verifiers.

Each verifier maps ``(answer, ground_truth) -> correctness in [0, 1]``.
Verifiers are pure functions: no network, no model calls, no randomness. This
keeps grading reproducible and auditable, which is the property a verification
subnet must have.
"""

from __future__ import annotations

import ast
import math
import re
from typing import Callable, Dict, List

from .base import GroundTruth

Verifier = Callable[[str, GroundTruth], float]

_VERIFIERS: Dict[str, Verifier] = {}


def verifier(name: str) -> Callable[[Verifier], Verifier]:
    def deco(fn: Verifier) -> Verifier:
        _VERIFIERS[name] = fn
        return fn

    return deco


def get_verifier(name: str) -> Verifier:
    if name not in _VERIFIERS:
        raise KeyError(f"unknown verifier '{name}'")
    return _VERIFIERS[name]


def available() -> List[str]:
    return sorted(_VERIFIERS)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def normalise(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[`*_\"']", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .")


def extract_number(text: str) -> float | None:
    """Pick the last number in a free-form answer ("the answer is 42.")."""
    cleaned = text.replace(",", "")
    matches = _NUM_RE.findall(cleaned)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:  # pragma: no cover - defensive
        return None


# --------------------------------------------------------------------------
# verifiers
# --------------------------------------------------------------------------
@verifier("exact")
def exact(answer: str, gt: GroundTruth) -> float:
    """Exact string match after normalisation, plus configured aliases."""
    a = normalise(answer)
    accepted = {normalise(gt.answer)}
    accepted |= {normalise(x) for x in gt.params.get("aliases", [])}
    return 1.0 if a in accepted else 0.0


@verifier("boolean")
def boolean(answer: str, gt: GroundTruth) -> float:
    """Yes/no verdicts. Rejects hedged answers containing both polarities."""
    a = normalise(answer)
    truthy = {"yes", "true", "vulnerable", "1", "correct", "valid", "buggy"}
    falsy = {"no", "false", "not vulnerable", "safe", "0", "incorrect", "invalid", "clean"}
    tokens = set(re.split(r"[^a-z0-9]+", a)) | {a}
    is_true = bool(tokens & truthy)
    is_false = bool(tokens & falsy)
    if is_true == is_false:  # ambiguous or empty
        return 0.0
    expected = normalise(gt.answer) in truthy
    return 1.0 if (is_true == expected) else 0.0


@verifier("numeric")
def numeric(answer: str, gt: GroundTruth) -> float:
    """Numeric equality within an absolute/relative tolerance."""
    got = extract_number(answer)
    if got is None or not math.isfinite(got):
        return 0.0
    try:
        want = float(gt.answer)
    except ValueError:  # pragma: no cover - generator bug
        return 0.0
    atol = float(gt.params.get("atol", 1e-6))
    rtol = float(gt.params.get("rtol", 1e-6))
    return 1.0 if math.isclose(got, want, rel_tol=rtol, abs_tol=atol) else 0.0


@verifier("set_match")
def set_match(answer: str, gt: GroundTruth) -> float:
    """Partial credit via F1 over an unordered set of tokens (e.g. anomalies)."""
    want = {normalise(x) for x in gt.params.get("items", []) if normalise(x)}
    got = {normalise(x) for x in re.split(r"[,\n;]+", answer) if normalise(x)}
    if not want:
        return 1.0 if not got else 0.0
    if not got:
        return 0.0
    tp = len(want & got)
    if tp == 0:
        return 0.0
    precision = tp / len(got)
    recall = tp / len(want)
    f1 = 2 * precision * recall / (precision + recall)
    # a partially correct set is worth partial credit, but only above a floor
    return round(f1, 6) if f1 >= float(gt.params.get("min_f1", 0.0)) else 0.0


@verifier("sequence")
def sequence(answer: str, gt: GroundTruth) -> float:
    """Ordered sequence match with positional partial credit."""
    want = [normalise(x) for x in gt.params.get("items", [])]
    got = [normalise(x) for x in re.split(r"[,>\n;]+|->", answer) if normalise(x)]
    if not want:
        return 0.0
    hits = sum(1 for i, w in enumerate(want) if i < len(got) and got[i] == w)
    score = hits / len(want)
    return 1.0 if score == 1.0 else round(score * 0.5, 6)  # partial credit halved


@verifier("multiple_choice")
def multiple_choice(answer: str, gt: GroundTruth) -> float:
    """Single-letter / option-label answers."""
    a = normalise(answer)
    want = normalise(gt.answer)
    if a == want:
        return 1.0
    m = re.match(r"^\(?([a-z])\)?\b", a)
    return 1.0 if m and m.group(1) == want else 0.0


@verifier("python_predicate")
def python_predicate(answer: str, gt: GroundTruth) -> float:
    """Programmatic verification: evaluate a sandboxed predicate on the answer.

    ``gt.params['predicate']`` is a python expression using only ``answer``
    (string), ``value`` (parsed number or ``None``) and the ``math`` module.
    Compiled with ``ast`` validation: no imports, no attribute access outside
    ``math``, no calls other than a small allowlist. This is a defence-in-depth
    measure — predicates are authored by the validator, never by miners.
    """
    expr = gt.params.get("predicate")
    if not expr:
        return 0.0
    if not _expression_is_safe(expr):
        raise ValueError("unsafe predicate expression rejected")
    env = {
        "answer": answer.strip(),
        "value": extract_number(answer),
        "math": math,
        "abs": abs,
        "len": len,
        "round": round,
        "min": min,
        "max": max,
        "float": float,
        "int": int,
        "str": str,
    }
    try:
        result = eval(compile(expr, "<predicate>", "eval"), {"__builtins__": {}}, env)  # noqa: S307
    except Exception:
        return 0.0
    if isinstance(result, bool):
        return 1.0 if result else 0.0
    try:
        return max(0.0, min(1.0, float(result)))
    except (TypeError, ValueError):
        return 0.0


_ALLOWED_CALLS = {"abs", "len", "round", "min", "max", "float", "int", "str",
                  "isclose", "sqrt", "log", "fabs"}


def _expression_is_safe(expr: str) -> bool:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Lambda,
                             ast.comprehension, ast.Await, ast.Yield)):
            return False
        if isinstance(node, ast.Attribute):
            if not (isinstance(node.value, ast.Name) and node.value.id == "math"):
                return False
        if isinstance(node, ast.Call):
            fn = node.func
            fname = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if fname not in _ALLOWED_CALLS:
                return False
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return False
    return True


def verify(answer: str, gt: GroundTruth) -> float:
    """Grade ``answer`` against hidden ``gt``; always returns a float in [0,1]."""
    if not answer or not answer.strip():
        return 0.0
    score = get_verifier(gt.verifier)(answer, gt)
    if score != score or score in (float("inf"), float("-inf")):  # NaN / inf guard
        return 0.0
    return max(0.0, min(1.0, float(score)))
