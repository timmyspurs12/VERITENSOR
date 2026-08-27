"""Mathematical reasoning tasks.

All problems are generated from random parameters and solved analytically at
generation time, so ground truth is exact and never drawn from a public
dataset that a miner could memorise.
"""

from __future__ import annotations

import math
import random
from fractions import Fraction
from typing import Optional

from ..protocol.messages import Category, VerificationType
from .base import BaseGenerator, GeneratedTask, GroundTruth, register

_NAMES = ["Ada", "Grace", "Alan", "Katherine", "Edsger", "Barbara", "Donald", "Radia"]
_ITEMS = ["sensors", "shards", "nodes", "batches", "packets", "replicas"]


@register
class LinearAlgebraicGenerator(BaseGenerator):
    """Solve a linear/quadratic equation with integer-friendly parameters."""

    name = "math.algebra"
    category = Category.MATH
    verification_type = VerificationType.EXACT
    default_timeout_s = 20

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        if difficulty <= 4:
            a, b, c = rng.randint(2, 29), rng.randint(-140, 140), rng.randint(-400, 400)
            x = Fraction(c - b, a)
            prompt = (
                f"Solve for x: {a}x + ({b}) = {c}. "
                "Give the exact value as a decimal (4 dp if not an integer)."
            )
            answer = _fmt(float(x))
            expl = f"x = ({c} - {b}) / {a} = {answer}"
        else:
            r1, r2 = rng.randint(-9, 9), rng.randint(-9, 9)
            a = rng.choice([1, 1, 2])
            b, c = -a * (r1 + r2), a * r1 * r2
            larger = max(r1, r2)
            prompt = (
                f"The quadratic {a}x^2 + ({b})x + ({c}) = 0 has two real roots. "
                "Report the LARGER root as a number."
            )
            answer = _fmt(float(larger))
            expl = f"Roots are {r1} and {r2}; larger = {larger}."
        gt = GroundTruth(answer=answer, verifier="numeric",
                         params={"atol": 1e-3, "rtol": 1e-4},
                         evidence_keywords=["isolate", "factor", "root", "substitute"],
                         explanation=expl)
        req = self.build_request(prompt, difficulty, answer_schema={"type": "number"})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate", "prompt": prompt,
                                            "answer": answer})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        return _restate_mutation(self, task, rng)


@register
class ProbabilityGenerator(BaseGenerator):
    """Discrete probability with an exactly computable answer."""

    name = "math.probability"
    category = Category.MATH
    verification_type = VerificationType.PROGRAMMATIC
    default_timeout_s = 25

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        red = rng.randint(3, 40)
        blue = rng.randint(3, 40)
        draw = 2 if difficulty <= 5 else 3
        total = red + blue
        if draw > total:
            draw = 2
        p = Fraction(math.comb(red, draw), math.comb(total, draw)) if red >= draw else Fraction(0)
        item = rng.choice(_ITEMS)
        prompt = (
            f"A rack holds {red} healthy {item} and {blue} degraded {item}. "
            f"{draw} are sampled uniformly at random without replacement. "
            "What is the probability that ALL sampled units are healthy? "
            "Answer as a decimal rounded to 4 decimal places."
        )
        answer = f"{float(p):.4f}"
        gt = GroundTruth(answer=answer, verifier="numeric",
                         params={"atol": 5e-4, "rtol": 0.0},
                         evidence_keywords=["combination", "without replacement",
                                            "hypergeometric", "c(n,k)"],
                         explanation=f"C({red},{draw})/C({total},{draw}) = {float(p):.6f}")
        req = self.build_request(prompt, difficulty, answer_schema={"type": "number"})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate", "prompt": prompt,
                                            "answer": answer})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        return _restate_mutation(self, task, rng)


@register
class NumericalReasoningGenerator(BaseGenerator):
    """Multi-step word problem (rates, percentages, compounding)."""

    name = "math.numerical"
    category = Category.MATH
    verification_type = VerificationType.EXACT

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        who = rng.choice(_NAMES)
        base = rng.randint(200, 20_000)
        pct = rng.choice([5, 8, 10, 12, 15, 20, 25])
        periods = 2 if difficulty <= 4 else rng.randint(3, 5)
        value = base * (1 + pct / 100) ** periods
        prompt = (
            f"{who}'s validator processes {base} verification tasks in epoch 0. "
            f"Throughput grows by {pct}% each epoch, compounding. "
            f"How many tasks are processed in epoch {periods}? "
            "Answer to 2 decimal places."
        )
        answer = f"{value:.2f}"
        gt = GroundTruth(answer=answer, verifier="numeric",
                         params={"atol": 0.05, "rtol": 1e-4},
                         evidence_keywords=["compound", "growth", "exponent", "percent"],
                         explanation=f"{base} * 1.{pct:02d}^{periods} = {value:.4f}")
        req = self.build_request(prompt, difficulty, answer_schema={"type": "number"})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate", "prompt": prompt,
                                            "answer": answer})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        return _restate_mutation(self, task, rng)


@register
class ModularArithmeticGenerator(BaseGenerator):
    """Number theory: modular exponentiation / gcd chains."""

    name = "math.modular"
    category = Category.MATH
    verification_type = VerificationType.PROGRAMMATIC

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        base = rng.randint(2, 400)
        exp = rng.randint(5, 60 + difficulty * 40)
        mod = rng.choice([97, 101, 103, 107, 109, 113, 127, 131, 137, 139,
                          149, 151, 157, 163, 167, 173, 179, 181, 191, 193])
        value = pow(base, exp, mod)
        prompt = (
            f"Compute {base}^{exp} mod {mod}. Answer with the integer only."
        )
        gt = GroundTruth(answer=str(value), verifier="numeric",
                         params={"atol": 0.0, "rtol": 0.0},
                         evidence_keywords=["fermat", "square", "modulus", "exponentiation"],
                         explanation=f"pow({base},{exp},{mod}) = {value}")
        req = self.build_request(prompt, difficulty, answer_schema={"type": "integer"})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate", "prompt": prompt,
                                            "answer": str(value)})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        return _restate_mutation(self, task, rng)


_REPHRASINGS = [
    "Re-stated variant (identical quantities, different wording):\n{p}",
    "{p}\n\n(Note: this is a paraphrase of an earlier item; the numeric answer is unchanged.)",
    "Consider the following problem.\n\n{p}\n\nProvide only the final value.",
]


def _restate_mutation(gen: BaseGenerator, task: GeneratedTask,
                      rng: random.Random) -> Optional[GeneratedTask]:
    spec = task.mutation_spec
    if spec.get("kind") != "restate":
        return None
    template = rng.choice(_REPHRASINGS)
    prompt = template.format(p=spec["prompt"])
    req = gen.build_request(prompt, task.request.difficulty,
                            verification_type=VerificationType.ADVERSARIAL,
                            parent_task_id=task.request.task_id)
    gt = GroundTruth(answer=task.ground_truth.answer,
                     verifier=task.ground_truth.verifier,
                     params=dict(task.ground_truth.params),
                     evidence_keywords=list(task.ground_truth.evidence_keywords),
                     explanation="Paraphrase mutation; answer invariant.")
    return GeneratedTask(request=req, ground_truth=gt, generator=gen.name,
                         mutation_spec=spec)


def _fmt(x: float) -> str:
    return str(int(x)) if abs(x - round(x)) < 1e-9 else f"{x:.4f}"
