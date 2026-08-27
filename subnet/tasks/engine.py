"""Task engine: seeded generation, benchmark rotation and mutation."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from ..protocol.messages import Category
from .base import GeneratedTask, registry


@dataclass(frozen=True, slots=True)
class RotationPolicy:
    """Mixture used by validators when drawing the next task.

    Benchmark rotation defends against memorisation: a miner never knows
    whether the current item is a fresh generated task, a held-out benchmark
    replay, or an adversarial mutation of something it already answered.
    """

    generated: float = 0.65
    hidden_benchmark: float = 0.15
    adversarial: float = 0.15
    mutation: float = 0.05

    def sample(self, rng: random.Random) -> str:
        buckets = [
            ("generated", self.generated),
            ("hidden_benchmark", self.hidden_benchmark),
            ("adversarial", self.adversarial),
            ("mutation", self.mutation),
        ]
        total = sum(w for _, w in buckets) or 1.0
        r = rng.random() * total
        upto = 0.0
        for name, weight in buckets:
            upto += weight
            if r <= upto:
                return name
        return "generated"


class TaskEngine:
    """Facade over all registered generators.

    Deterministic: given the same ``seed`` the same task text and ground truth
    are produced, which makes simulations reproducible for judges while still
    being unpredictable to miners (ids and nonces stay CSPRNG-generated).
    """

    def __init__(self, seed: Optional[int] = None,
                 rotation: Optional[RotationPolicy] = None) -> None:
        self._rng = random.Random(seed)
        self.rotation = rotation or RotationPolicy()

    # -- introspection ----------------------------------------------------
    @property
    def generators(self) -> Dict[str, object]:
        return registry()

    def generator_names(self, category: Optional[Category] = None) -> List[str]:
        return sorted(
            name for name, gen in registry().items()
            if category is None or gen.category == category
        )

    # -- generation -------------------------------------------------------
    @staticmethod
    def _is_benchmark(name: str) -> bool:
        return name.startswith("benchmark.")

    def generate(self, category: Optional[Category] = None, difficulty: int = 5,
                 generator: Optional[str] = None,
                 seed: Optional[int] = None,
                 include_benchmarks: bool = False) -> GeneratedTask:
        """Draw a task.

        Held-out benchmark generators are excluded by default: they are served
        only when the rotation policy asks for them (see ``generate_benchmark``),
        which is what keeps the private bank private and rare.
        """
        rng = random.Random(seed) if seed is not None else self._rng
        pool = [g for g in registry().values()
                if (category is None or g.category == category)
                and (generator is None or g.name == generator)
                and (include_benchmarks or generator is not None
                     or not self._is_benchmark(g.name))]
        if not pool:
            raise ValueError(f"no generator for category={category} name={generator}")
        gen = rng.choice(pool)
        task = gen.generate(int(max(1, min(10, difficulty))), rng)
        task.ground_truth.seed = seed if seed is not None else -1
        return task

    def generate_batch(self, count: int, categories: Optional[Sequence[Category]] = None,
                       difficulty: int = 5) -> List[GeneratedTask]:
        cats = list(categories) if categories else list(Category)
        return [self.generate(self._rng.choice(cats), difficulty) for _ in range(count)]

    def generate_benchmark(self, category: Optional[Category] = None,
                           difficulty: int = 5) -> Optional[GeneratedTask]:
        """Serve a held-out benchmark item, or ``None`` if the bank has none."""
        candidates = [g for g in registry().values()
                      if self._is_benchmark(g.name)
                      and (category is None or g.category == category)]
        if not candidates:
            return None
        gen = self._rng.choice(candidates)
        return gen.generate(int(max(1, min(10, difficulty))), self._rng)

    def has_benchmarks(self, category: Optional[Category] = None) -> bool:
        return any(self._is_benchmark(g.name)
                   and (category is None or g.category == category)
                   for g in registry().values())

    def mutate(self, task: GeneratedTask) -> Optional[GeneratedTask]:
        gen = registry().get(task.generator)
        if gen is None:
            return None
        return gen.mutate(task, self._rng)

    def draw_kind(self) -> str:
        return self.rotation.sample(self._rng)
