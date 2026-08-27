"""Logical reasoning tasks with deterministic answers.

Each generator builds a hidden ground-truth structure first (an ordering, an
assignment, a rule) and then renders a subset of constraints that uniquely
determines it. Uniqueness is checked by brute-force search at generation time,
so a task is never published unless exactly one solution exists.
"""

from __future__ import annotations

import itertools
import random
from typing import Dict, List, Optional, Tuple

from ..protocol.messages import Category, VerificationType
from .base import BaseGenerator, GeneratedTask, GroundTruth, register

_AGENTS = ["Alpha", "Bravo", "Cirrus", "Delta", "Echo", "Fermi", "Gauss"]
_SLOTS = ["region-1", "region-2", "region-3", "region-4", "region-5"]


@register
class OrderingGenerator(BaseGenerator):
    """Recover a unique total order from pairwise/positional constraints."""

    name = "reasoning.ordering"
    category = Category.REASONING
    verification_type = VerificationType.EXACT
    default_timeout_s = 30

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        n = 4 if difficulty <= 4 else (5 if difficulty <= 7 else 6)
        agents = rng.sample(_AGENTS, n)
        truth = agents[:]
        rng.shuffle(truth)
        constraints: List[str] = []
        clauses: List[Tuple[str, str, str]] = []
        # add constraints until the solution is unique (bounded attempts)
        for _ in range(40):
            if _unique_solution(agents, clauses) == truth:
                break
            a, b = rng.sample(truth, 2)
            if truth.index(a) > truth.index(b):
                a, b = b, a
            kind = rng.choice(["before", "immediately_before", "position"])
            if kind == "position":
                who = rng.choice(truth)
                clauses.append(("position", who, str(truth.index(who) + 1)))
                constraints.append(f"{who} finished in position {truth.index(who) + 1}.")
            elif kind == "immediately_before" and truth.index(b) == truth.index(a) + 1:
                clauses.append(("immediately_before", a, b))
                constraints.append(f"{a} finished immediately before {b}.")
            else:
                clauses.append(("before", a, b))
                constraints.append(f"{a} finished somewhere before {b}.")
        rng.shuffle(constraints)
        prompt = (
            f"{n} miners ({', '.join(sorted(agents))}) finished a verification round in a "
            "strict order with no ties. Given:\n"
            + "\n".join(f"  {i+1}. {c}" for i, c in enumerate(constraints))
            + "\n\nList the finishing order from first to last, comma separated."
        )
        gt = GroundTruth(
            answer=", ".join(truth), verifier="sequence",
            params={"items": truth},
            evidence_keywords=["constraint", "position", "before", "elimination"],
            explanation="Unique order satisfying all constraints.",
        )
        req = self.build_request(prompt, difficulty,
                                 answer_schema={"type": "ordered_list", "length": n})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "reorder", "constraints": constraints,
                                            "agents": agents, "truth": truth, "n": n})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        spec = task.mutation_spec
        if spec.get("kind") != "reorder":
            return None
        constraints = spec["constraints"][:]
        rng.shuffle(constraints)  # irrelevant reordering, same solution
        prompt = (
            f"{spec['n']} miners ({', '.join(sorted(spec['agents']))}) finished in a strict "
            "order. Constraints (restated):\n"
            + "\n".join(f"  - {c}" for c in constraints)
            + "\n\nList the finishing order from first to last, comma separated."
        )
        req = self.build_request(prompt, task.request.difficulty,
                                 verification_type=VerificationType.ADVERSARIAL,
                                 parent_task_id=task.request.task_id)
        gt = GroundTruth(answer=task.ground_truth.answer, verifier="sequence",
                         params=dict(task.ground_truth.params),
                         explanation="Constraint order shuffled; solution invariant.")
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec=spec)


def _satisfies(order: Tuple[str, ...], clauses: List[Tuple[str, str, str]]) -> bool:
    idx = {a: i for i, a in enumerate(order)}
    for kind, a, b in clauses:
        if kind == "before" and not idx[a] < idx[b]:
            return False
        if kind == "immediately_before" and idx[b] - idx[a] != 1:
            return False
        if kind == "position" and idx[a] != int(b) - 1:
            return False
    return True


def _unique_solution(agents: List[str],
                     clauses: List[Tuple[str, str, str]]) -> Optional[List[str]]:
    if not clauses:
        return None
    found = None
    for perm in itertools.permutations(agents):
        if _satisfies(perm, clauses):
            if found is not None:
                return None
            found = list(perm)
    return found


@register
class ConstraintSatisfactionGenerator(BaseGenerator):
    """Assign agents to slots under exclusion constraints; unique solution."""

    name = "reasoning.constraints"
    category = Category.REASONING
    verification_type = VerificationType.EXACT

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        n = 3 if difficulty <= 4 else (4 if difficulty <= 7 else 5)
        agents = rng.sample(_AGENTS, n)
        slots = _SLOTS[:n]
        truth = dict(zip(agents, rng.sample(slots, n)))
        clauses: List[Tuple[str, str, bool]] = []
        statements: List[str] = []
        for _ in range(30):
            sols = _unique_assignment(agents, slots, clauses)
            if sols == truth:
                break
            agent = rng.choice(agents)
            if rng.random() < 0.5:
                clauses.append((agent, truth[agent], True))
                statements.append(f"{agent} is deployed in {truth[agent]}.")
            else:
                wrong = rng.choice([s for s in slots if s != truth[agent]])
                clauses.append((agent, wrong, False))
                statements.append(f"{agent} is NOT deployed in {wrong}.")
        rng.shuffle(statements)
        target = rng.choice(agents)
        prompt = (
            f"Each of {n} validators ({', '.join(sorted(agents))}) is deployed in exactly one "
            f"distinct region ({', '.join(slots)}).\n"
            + "\n".join(f"  - {s}" for s in statements)
            + f"\n\nWhich region hosts {target}? Answer with the region identifier only."
        )
        gt = GroundTruth(answer=truth[target], verifier="exact",
                         evidence_keywords=["exclusion", "elimination", "unique", "assignment"],
                         explanation=f"Unique assignment: {truth}")
        req = self.build_request(prompt, difficulty, answer_schema={"type": "string"})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate_cs", "statements": statements,
                                            "agents": agents, "slots": slots,
                                            "target": target, "n": n})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        spec = task.mutation_spec
        if spec.get("kind") != "restate_cs":
            return None
        statements = spec["statements"][:]
        rng.shuffle(statements)
        prompt = (
            f"{spec['n']} validators ({', '.join(sorted(spec['agents']))}) occupy distinct "
            f"regions ({', '.join(spec['slots'])}). Facts, in a different order:\n"
            + "\n".join(f"  * {s}" for s in statements)
            + f"\n\nState the region of {spec['target']}."
        )
        req = self.build_request(prompt, task.request.difficulty,
                                 verification_type=VerificationType.ADVERSARIAL,
                                 parent_task_id=task.request.task_id)
        gt = GroundTruth(answer=task.ground_truth.answer, verifier="exact",
                         explanation="Fact order shuffled; assignment invariant.")
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec=spec)


def _unique_assignment(agents, slots, clauses) -> Optional[Dict[str, str]]:
    if not clauses:
        return None
    found = None
    for perm in itertools.permutations(slots, len(agents)):
        cand = dict(zip(agents, perm))
        ok = all((cand[a] == s) == positive for a, s, positive in clauses)
        if ok:
            if found is not None:
                return None
            found = cand
    return found


@register
class PatternGenerator(BaseGenerator):
    """Infer the rule of a generated integer sequence and continue it."""

    name = "reasoning.pattern"
    category = Category.REASONING
    verification_type = VerificationType.PROGRAMMATIC

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        kind = rng.choice(["affine", "poly", "fib"])
        a, b = rng.randint(2, 7), rng.randint(1, 40)
        seq: List[int] = []
        if kind == "affine":
            x = rng.randint(1, 60)
            for _ in range(6):
                seq.append(x)
                x = a * x + b
            rule = f"x -> {a}x + {b}"
        elif kind == "poly":
            for i in range(1, 7):
                seq.append(a * i * i + b * i)
            rule = f"n -> {a}n^2 + {b}n"
        else:
            p, q = rng.randint(1, 40), rng.randint(1, 40)
            for _ in range(6):
                seq.append(p)
                p, q = q, p + q
            rule = "Fibonacci-like recurrence"
        nxt = _continue(seq, kind, a, b)
        prompt = (
            "Continue the sequence with the next single integer:\n\n  "
            + ", ".join(str(s) for s in seq)
            + ", ?\n\nAnswer with the integer only."
        )
        gt = GroundTruth(answer=str(nxt), verifier="numeric",
                         params={"atol": 0.0, "rtol": 0.0},
                         evidence_keywords=["difference", "recurrence", "rule", "ratio"],
                         explanation=f"Rule: {rule}; next term = {nxt}.")
        req = self.build_request(prompt, difficulty, answer_schema={"type": "integer"})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate", "prompt": prompt,
                                            "answer": str(nxt)})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        from .math_tasks import _restate_mutation

        return _restate_mutation(self, task, rng)


def _continue(seq: List[int], kind: str, a: int, b: int) -> int:
    if kind == "affine":
        return a * seq[-1] + b
    if kind == "poly":
        n = len(seq) + 1
        return a * n * n + b * n
    return seq[-1] + seq[-2]  # fib-like
