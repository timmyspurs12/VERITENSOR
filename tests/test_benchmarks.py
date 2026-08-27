"""Held-out benchmark bank and benchmark rotation."""

import json
from pathlib import Path

import pytest

from benchmarks import load_bank, register_benchmark_generators
from subnet.protocol.messages import Category
from subnet.tasks import TaskEngine, verify

BANK = Path(__file__).resolve().parents[1] / "benchmarks"


def test_bank_loads_every_family():
    bank = load_bank()
    assert bank.count() >= 15
    for category in Category:
        assert bank.for_category(category), f"no benchmark items for {category}"


def test_every_benchmark_item_self_verifies():
    """A stored answer that does not satisfy its own verifier is a data bug."""
    register_benchmark_generators()
    import random

    rng = random.Random(0)
    for gen in register_benchmark_generators():
        for _ in range(20):
            task = gen.generate(6, rng)
            assert verify(task.ground_truth.answer, task.ground_truth) == 1.0, \
                f"{gen.name}: {task.ground_truth.answer!r}"


def test_benchmark_items_are_excluded_from_the_generated_pool():
    """The private bank must not leak into ordinary generation."""
    register_benchmark_generators()
    engine = TaskEngine(seed=11)
    for _ in range(200):
        assert not engine.generate(difficulty=5).generator.startswith("benchmark.")


def test_benchmarks_are_served_only_on_request():
    register_benchmark_generators()
    engine = TaskEngine(seed=12)
    task = engine.generate_benchmark(Category.MATH, 6)
    assert task is not None and task.generator == "benchmark.math"
    assert engine.has_benchmarks(Category.CODE)


def test_benchmark_answers_are_not_readable_from_the_prompt():
    """The answer must not appear verbatim in the prompt.

    Enumerated-option items (yes/no, A–D, "region-1 | region-2 | region-3") are
    excluded: there the label necessarily appears because every option is
    offered, so its presence carries no information about which one is correct.
    """
    register_benchmark_generators()
    import random

    rng = random.Random(3)
    # set_match answers are row identifiers that must appear in the supplied table
    open_ended = {"numeric", "sequence"}
    checked = 0
    for gen in register_benchmark_generators():
        for _ in range(12):
            task = gen.generate(6, rng)
            if task.ground_truth.verifier not in open_ended:
                continue
            assert task.ground_truth.answer.lower() not in task.request.prompt.lower()
            checked += 1
    assert checked > 15


def test_rotation_actually_mixes_kinds(network):
    from subnet.simulation import SimulationConfig

    network.run_simulation(SimulationConfig(tasks=120, difficulty_mode="normal"))
    kinds = {t.kind for t in network.tasks}
    assert "generated" in kinds
    assert len(kinds) >= 2, f"benchmark rotation produced only {kinds}"


def test_bank_json_is_wellformed():
    for path in BANK.rglob("*.json"):
        payload = json.loads(path.read_text())
        assert payload["items"], path
        ids = [i["id"] for i in payload["items"]]
        assert len(ids) == len(set(ids)), f"duplicate ids in {path}"
        for item in payload["items"]:
            assert 1 <= item["difficulty"] <= 10
            assert item["prompt"].strip() and str(item["answer"]).strip()
