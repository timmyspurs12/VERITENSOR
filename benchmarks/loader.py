"""Loader that turns the JSON benchmark bank into task generators.

Each family becomes a ``BenchmarkGenerator`` registered under
``benchmark.<family>``. The task engine can then draw a held-out item exactly
like any generated task — same protocol, same verifiers, same scoring — while
the item text and its answer never enter the generated pool.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from subnet.protocol.messages import Category, VerificationType
from subnet.tasks.base import BaseGenerator, GeneratedTask, GroundTruth, register

BANK_DIR = Path(__file__).resolve().parent
FAMILY_DIRS = {
    Category.CODE: "code",
    Category.MATH: "math",
    Category.REASONING: "reasoning",
    Category.DATA: "data",
}


@dataclass(frozen=True, slots=True)
class BenchmarkItem:
    id: str
    difficulty: int
    prompt: str
    answer: str
    verifier: str
    params: dict
    keywords: List[str]
    explanation: str


@dataclass(slots=True)
class BenchmarkBank:
    items: Dict[Category, List[BenchmarkItem]]

    def count(self) -> int:
        return sum(len(v) for v in self.items.values())

    def for_category(self, category: Category) -> List[BenchmarkItem]:
        return self.items.get(category, [])


def load_bank(directory: Optional[Path] = None) -> BenchmarkBank:
    root = directory or BANK_DIR
    items: Dict[Category, List[BenchmarkItem]] = {}
    for category, folder in FAMILY_DIRS.items():
        path = root / folder
        if not path.is_dir():
            continue
        bucket: List[BenchmarkItem] = []
        for file in sorted(path.glob("*.json")):
            payload = json.loads(file.read_text())
            for raw in payload.get("items", []):
                bucket.append(BenchmarkItem(
                    id=raw["id"], difficulty=int(raw.get("difficulty", 5)),
                    prompt=raw["prompt"], answer=str(raw["answer"]),
                    verifier=raw.get("verifier", "exact"),
                    params=raw.get("params", {}),
                    keywords=raw.get("keywords", []),
                    explanation=raw.get("explanation", "")))
        if bucket:
            items[category] = bucket
    return BenchmarkBank(items=items)


class BenchmarkGenerator(BaseGenerator):
    """Serves a held-out item as a protocol-compliant task."""

    verification_type = VerificationType.EXACT
    default_timeout_s = 30

    def __init__(self, category: Category, items: List[BenchmarkItem]) -> None:
        self.category = category
        self.name = f"benchmark.{category.value}"
        self._items = items

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        # prefer items near the requested difficulty, but never fail
        pool = [i for i in self._items if abs(i.difficulty - difficulty) <= 2] \
            or self._items
        item = rng.choice(pool)
        request = self.build_request(item.prompt, item.difficulty)
        gt = GroundTruth(answer=item.answer, verifier=item.verifier,
                         params=dict(item.params),
                         evidence_keywords=list(item.keywords),
                         explanation=item.explanation)
        return GeneratedTask(request=request, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate",
                                            "prompt": item.prompt,
                                            "answer": item.answer,
                                            "benchmark_id": item.id})

    def mutate(self, task: GeneratedTask, rng: random.Random):
        from subnet.tasks.math_tasks import _restate_mutation

        return _restate_mutation(self, task, rng)


_generators: List[BenchmarkGenerator] = []


def benchmark_generators() -> List[BenchmarkGenerator]:
    return list(_generators)


def register_benchmark_generators(bank: Optional[BenchmarkBank] = None
                                  ) -> List[BenchmarkGenerator]:
    """Register one generator per non-empty family (idempotent)."""
    global _generators
    if _generators:
        return _generators
    bank = bank or load_bank()
    for category, items in bank.items.items():
        gen = BenchmarkGenerator(category, items)
        register(gen)
        _generators.append(gen)
    return _generators
