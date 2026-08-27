"""Anti-gaming: replay protection, duplicates, rate limits, evidence reuse."""

from datetime import datetime, timedelta, timezone

import pytest

from subnet.protocol.messages import Evidence, MinerResponse, TaskRequest
from subnet.protocol.signing import (new_nonce, new_task_id, task_commitment,
                                     verify_commitment)
from subnet.scoring.antigaming import AntiGamingGuard, RateLimitRule
from subnet.tasks import TaskEngine


def make_task(engine=None, schema=None):
    engine = engine or TaskEngine(seed=5)
    task = engine.generate(difficulty=5)
    if schema is not None:
        task.request.answer_schema = schema
    return task


def make_response(task: TaskRequest, uid=1, answer="alpha beta gamma delta",
                  evidence=("checked the constraints carefully",), nonce=None):
    return MinerResponse(
        task_id=task.task_id, miner_uid=uid, nonce=nonce or task.nonce,
        answer=answer, confidence=0.8, execution_time_ms=500,
        evidence=[Evidence(kind="reasoning", content=e) for e in evidence])


def test_response_for_another_task_is_rejected():
    engine = TaskEngine(seed=1)
    a, b = make_task(engine), make_task(engine)
    guard = AntiGamingGuard()
    guard.register_task(a.request)
    guard.register_task(b.request)
    stolen = make_response(b.request)
    report = guard.inspect(stolen, a.request)
    assert report.rejected and report.reason == "task_id_mismatch"
    assert "replay_attempt" in report.penalties


def test_wrong_nonce_is_rejected():
    task = make_task()
    guard = AntiGamingGuard()
    guard.register_task(task.request)
    bad = make_response(task.request, nonce=new_nonce())
    report = guard.inspect(bad, task.request)
    assert report.rejected and report.reason == "nonce_mismatch"


def test_same_response_cannot_be_submitted_twice():
    task = make_task()
    guard = AntiGamingGuard()
    guard.register_task(task.request)
    r = make_response(task.request)
    assert not guard.inspect(r, task.request).rejected
    second = guard.inspect(r, task.request)
    assert second.rejected and second.reason == "duplicate_submission"


def test_late_response_is_penalised():
    task = make_task()
    guard = AntiGamingGuard()
    guard.register_task(task.request)
    r = make_response(task.request)
    r.submitted_at = task.request.deadline + timedelta(seconds=5)
    report = guard.inspect(r, task.request)
    assert "deadline_miss" in report.flags


def test_repeated_identical_answers_are_penalised():
    engine = TaskEngine(seed=9)
    guard = AntiGamingGuard()
    flagged = False
    for _ in range(8):
        task = make_task(engine, schema={"type": "string"})
        guard.register_task(task.request)
        report = guard.inspect(make_response(task.request, answer="the same answer"),
                               task.request)
        flagged = flagged or "duplicate_response" in report.flags
    assert flagged


def test_enum_answers_are_not_flagged_as_duplicates_too_early():
    """Yes/no answers repeat legitimately; the detector must not punish that."""
    engine = TaskEngine(seed=11)
    guard = AntiGamingGuard()
    for _ in range(8):
        task = make_task(engine, schema={"type": "enum", "values": ["YES", "NO"]})
        guard.register_task(task.request)
        report = guard.inspect(make_response(task.request, answer="YES"), task.request)
        assert "duplicate_response" not in report.flags


def test_identical_evidence_is_flagged_as_boilerplate():
    engine = TaskEngine(seed=13)
    guard = AntiGamingGuard()
    flags = []
    for i in range(4):
        task = make_task(engine)
        guard.register_task(task.request)
        report = guard.inspect(
            make_response(task.request, answer=f"answer-{i}",
                          evidence=("identical reasoning text",)), task.request)
        flags.extend(report.flags)
    assert "boilerplate_evidence" in flags


def test_cross_miner_identical_evidence_flags_collusion():
    task = make_task()
    guard = AntiGamingGuard()
    guard.register_task(task.request)
    flags = []
    for uid in range(4):
        report = guard.inspect(
            make_response(task.request, uid=uid, answer=f"a{uid}",
                          evidence=("word for word identical rationale",)),
            task.request)
        flags.extend(report.flags)
    assert "evidence_collusion" in flags


def test_rate_limiter_blocks_burst():
    guard = AntiGamingGuard(rate_rule=RateLimitRule(max_requests=5, per_seconds=60))
    allowed = sum(1 for _ in range(20) if guard.check_rate(7))
    assert allowed == 5


def test_rate_limit_is_per_miner():
    guard = AntiGamingGuard(rate_rule=RateLimitRule(max_requests=2, per_seconds=60))
    assert guard.check_rate(1) and guard.check_rate(1) and not guard.check_rate(1)
    assert guard.check_rate(2)


def test_commitment_binds_ground_truth():
    tid, nonce = new_task_id(), new_nonce()
    c = task_commitment(tid, nonce, "42", "secret")
    assert verify_commitment(c, tid, nonce, "42", "secret")
    assert not verify_commitment(c, tid, nonce, "43", "secret")
    assert not verify_commitment(c, tid, nonce, "42", "other-secret")


def test_gaming_miner_is_ranked_last_by_the_mechanism(network):
    """End-to-end: the gaming profile must not out-earn honest miners."""
    from subnet.simulation.network import SimulationConfig

    net = network
    net.register_miner("gaming", name="Farmer")
    net.register_miner("high_quality", name="Honest")
    net.run_simulation(SimulationConfig(miners=len(net.miners), validators=2,
                                        tasks=60, difficulty_mode="normal"))
    board = {row["name"]: row for row in net.leaderboard()}
    assert board["Farmer"]["reputation"] < board["Honest"]["reputation"]
    assert board["Farmer"]["emission_weight"] < board["Honest"]["emission_weight"]
    assert board["Farmer"]["flags"], "gaming behaviour should raise flags"
