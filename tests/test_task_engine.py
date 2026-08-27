"""Task generation + hidden ground-truth verification."""

import random

import pytest

from subnet.protocol.messages import Category, VerificationType
from subnet.tasks import TaskEngine, verify
from subnet.tasks.verifiers import available


@pytest.mark.parametrize("category", list(Category))
def test_every_category_has_generators(task_engine, category):
    assert task_engine.generator_names(category), f"no generator for {category}"


@pytest.mark.parametrize("category", list(Category))
def test_generated_tasks_self_verify(task_engine, category):
    """The declared ground truth must score 1.0 under its own verifier."""
    for difficulty in range(1, 11):
        task = task_engine.generate(category, difficulty)
        assert verify(task.ground_truth.answer, task.ground_truth) == 1.0
        assert 1 <= task.request.difficulty <= 10
        assert task.request.prompt.strip()


def test_task_ids_and_nonces_are_unique_and_long(task_engine):
    ids, nonces = set(), set()
    for _ in range(200):
        t = task_engine.generate(difficulty=5)
        ids.add(t.request.task_id)
        nonces.add(t.request.nonce)
        assert len(t.request.nonce) >= 32
    assert len(ids) == 200
    assert len(nonces) == 200


def test_enum_prompts_are_symmetric(task_engine):
    """A miner must not be able to read the verdict out of the prompt.

    Both verdict labels are always offered, so the presence of a label carries
    no information about the hidden answer.
    """
    pairs = [("vulnerable", "safe"), ("buggy", "correct")]
    checked = 0
    for _ in range(80):
        t = task_engine.generate(Category.CODE, 5)
        if t.ground_truth.verifier != "boolean":
            continue
        prompt = t.request.prompt.lower()
        pair = next(p for p in pairs if p[0] in prompt or p[1] in prompt)
        assert pair[0] in prompt and pair[1] in prompt
        checked += 1
    assert checked > 10


def test_generation_is_reproducible_given_a_seed():
    a = TaskEngine(seed=42).generate(Category.MATH, 6, seed=7)
    b = TaskEngine(seed=42).generate(Category.MATH, 6, seed=7)
    assert a.request.prompt == b.request.prompt
    assert a.ground_truth.answer == b.ground_truth.answer
    assert a.request.task_id != b.request.task_id  # ids stay unpredictable


def test_mutations_preserve_ground_truth(task_engine):
    mutated_count = 0
    for _ in range(80):
        t = task_engine.generate(difficulty=5)
        m = task_engine.mutate(t)
        if m is None:
            continue
        mutated_count += 1
        assert m.ground_truth.answer == t.ground_truth.answer
        assert m.request.parent_task_id == t.request.task_id
        assert m.request.verification_type == VerificationType.ADVERSARIAL
        assert m.request.prompt != t.request.prompt
        assert verify(m.ground_truth.answer, m.ground_truth) == 1.0
    assert mutated_count > 40, "mutation engine covers too few generators"


def test_wrong_answers_are_rejected(task_engine):
    from subnet.miner.oracle import AnswerOracle

    oracle = AnswerOracle(random.Random(3))
    rejected = 0
    for _ in range(120):
        t = task_engine.generate(difficulty=5)
        score = verify(oracle.wrong(t.ground_truth), t.ground_truth)
        rejected += score < 1.0
    assert rejected >= 110  # a few partial-credit collisions are acceptable


def test_verifier_registry_is_complete():
    for name in ("exact", "boolean", "numeric", "set_match", "sequence",
                 "python_predicate"):
        assert name in available()


def test_unsafe_predicate_is_rejected():
    from subnet.tasks.base import GroundTruth
    from subnet.tasks.verifiers import python_predicate

    gt = GroundTruth(answer="1", verifier="python_predicate",
                     params={"predicate": "__import__('os').system('id')"})
    with pytest.raises(ValueError):
        python_predicate("1", gt)


def test_empty_answer_scores_zero(task_engine):
    t = task_engine.generate(difficulty=4)
    assert verify("", t.ground_truth) == 0.0
    assert verify("   ", t.ground_truth) == 0.0
