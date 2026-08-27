"""Transport tests — btauth/1 signed HTTP between validator and miner.

These run against the **installed Bittensor SDK** with real (unfunded) local
wallets. They exercise the same code path a testnet deployment uses; only the
chain is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from subnet.chain.sdk import probe
from subnet.chain.wallets import WalletRef, ensure_wallet
from subnet.protocol.messages import Category, MinerResponse, TaskRequest
from subnet.tasks import TaskEngine
from subnet.transport.btauth import (TransportAuthError, new_nonce_store,
                                     sign_request, verify_request)
from subnet.transport.client import MinerEndpoint, ValidatorClient
from subnet.transport.server import MinerServer, build_miner_app

sdk_required = pytest.mark.skipif(not probe().usable_for_transport,
                                  reason="bittensor SDK with http_auth not installed")


@pytest.fixture(scope="module")
def wallets(tmp_path_factory):
    path = tmp_path_factory.mktemp("wallets")
    validator = ensure_wallet(WalletRef("vt-test", "validator-00", str(path)),
                              allow_create=True)
    miner = ensure_wallet(WalletRef("vt-test", "miner-00", str(path)),
                          allow_create=True)
    other = ensure_wallet(WalletRef("vt-test", "miner-01", str(path)),
                          allow_create=True)
    return {"validator": validator, "miner": miner, "other": other}


@pytest.fixture
def task() -> TaskRequest:
    return TaskEngine(seed=11).generate(Category.MATH, 4).request


# ---------------------------------------------------------------- signing
@sdk_required
def test_sign_and_verify_round_trip(wallets, task):
    body = task.model_dump_json().encode()
    headers = sign_request(wallets["validator"], method="POST", path="/x",
                           body=body,
                           receiver_ss58=wallets["miner"].hotkey.ss58_address)
    caller = verify_request(headers, body, method="POST", path="/x",
                            self_hotkey_ss58=wallets["miner"].hotkey.ss58_address)
    assert caller.signed
    assert caller.hotkey_ss58 == wallets["validator"].hotkey.ss58_address


@sdk_required
def test_tampered_body_is_rejected(wallets):
    headers = sign_request(wallets["validator"], method="POST", path="/x",
                           body=b'{"a":1}',
                           receiver_ss58=wallets["miner"].hotkey.ss58_address)
    with pytest.raises(TransportAuthError) as exc:
        verify_request(headers, b'{"a":2}', method="POST", path="/x",
                       self_hotkey_ss58=wallets["miner"].hotkey.ss58_address)
    assert exc.value.reason == "bad_signature"


@sdk_required
def test_request_bound_to_another_miner_is_rejected(wallets):
    """A captured request cannot be replayed against a different miner."""
    body = b'{"a":1}'
    headers = sign_request(wallets["validator"], method="POST", path="/x",
                           body=body,
                           receiver_ss58=wallets["miner"].hotkey.ss58_address)
    with pytest.raises(TransportAuthError) as exc:
        verify_request(headers, body, method="POST", path="/x",
                       self_hotkey_ss58=wallets["other"].hotkey.ss58_address)
    assert exc.value.reason == "wrong_receiver"


@sdk_required
def test_replayed_nonce_is_rejected(wallets):
    body = b'{"a":1}'
    store = new_nonce_store()
    headers = sign_request(wallets["validator"], method="POST", path="/x",
                           body=body,
                           receiver_ss58=wallets["miner"].hotkey.ss58_address)
    kwargs = dict(method="POST", path="/x",
                  self_hotkey_ss58=wallets["miner"].hotkey.ss58_address,
                  nonce_store=store)
    verify_request(headers, body, **kwargs)
    with pytest.raises(TransportAuthError) as exc:
        verify_request(headers, body, **kwargs)
    assert exc.value.reason == "replay"


@sdk_required
def test_path_binding_is_enforced(wallets):
    body = b'{"a":1}'
    headers = sign_request(wallets["validator"], method="POST", path="/verify",
                           body=body,
                           receiver_ss58=wallets["miner"].hotkey.ss58_address)
    with pytest.raises(TransportAuthError):
        verify_request(headers, body, method="POST", path="/admin",
                       self_hotkey_ss58=wallets["miner"].hotkey.ss58_address)


def test_unsigned_requests_are_refused_unless_explicitly_enabled():
    from subnet.transport.btauth import unsigned_headers

    headers = unsigned_headers("dev")
    with pytest.raises(TransportAuthError) as exc:
        verify_request(headers, b"", method="POST", path="/x",
                       self_hotkey_ss58="x", allow_unsigned=False)
    assert exc.value.reason == "unsigned_rejected"
    caller = verify_request(headers, b"", method="POST", path="/x",
                            self_hotkey_ss58="x", allow_unsigned=True)
    assert caller.signed is False


# ---------------------------------------------------------------- server
def _solver_app(**kwargs):
    from fastapi.testclient import TestClient

    engine = TaskEngine(seed=3)

    def solve(task: TaskRequest):
        from subnet.miner.solvers import HeuristicSolver

        solution = HeuristicSolver().solve(task)
        return solution.as_response(task, kwargs.get("uid", 0), 42, "test")

    server = MinerServer(uid=kwargs.get("uid", 0), name="test-miner",
                         solver=solve, **{k: v for k, v in kwargs.items()
                                          if k != "uid"})
    return server, TestClient(build_miner_app(server))


def test_health_is_unauthenticated_and_advertises_the_hotkey():
    server, client = _solver_app(allow_unsigned=True, hotkey_ss58="5Fake")
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["hotkey_ss58"] == "5Fake"
    assert body["protocol"] == "veritensor/1"


def test_protocol_endpoint_requires_authentication():
    server, client = _solver_app(allow_unsigned=False, hotkey_ss58="5Fake")
    task = TaskEngine(seed=1).generate(Category.MATH, 3).request
    res = client.post("/veritensor/v1/verify", content=task.model_dump_json())
    assert res.status_code == 401
    assert server.stats.rejected


def test_miner_solves_an_authenticated_task_and_returns_a_valid_response():
    server, client = _solver_app(allow_unsigned=True)
    from subnet.transport.btauth import unsigned_headers

    generated = TaskEngine(seed=5).generate(Category.MATH, 4)
    res = client.post("/veritensor/v1/verify",
                      content=generated.request.model_dump_json(),
                      headers={**unsigned_headers("dev"),
                               "content-type": "application/json"})
    assert res.status_code == 200
    response = MinerResponse.model_validate(res.json())
    assert response.task_id == generated.request.task_id
    assert response.nonce == generated.request.nonce      # replay binding echoed
    assert 0.0 <= response.confidence <= 1.0
    assert server.stats.solved == 1


def test_malformed_task_is_rejected_without_running_the_solver():
    server, client = _solver_app(allow_unsigned=True)
    from subnet.transport.btauth import unsigned_headers

    res = client.post("/veritensor/v1/verify", content=b'{"not":"a task"}',
                      headers={**unsigned_headers("dev"),
                               "content-type": "application/json"})
    assert res.status_code == 422
    assert server.stats.solved == 0
    assert server.stats.rejected.get("malformed_task") == 1


def test_expired_task_is_refused():
    from datetime import datetime, timedelta, timezone

    server, client = _solver_app(allow_unsigned=True)
    from subnet.transport.btauth import unsigned_headers

    generated = TaskEngine(seed=5).generate(Category.MATH, 4)
    expired = generated.request.model_copy(update={
        "deadline": datetime.now(timezone.utc) - timedelta(seconds=5)})
    res = client.post("/veritensor/v1/verify", content=expired.model_dump_json(),
                      headers={**unsigned_headers("dev"),
                               "content-type": "application/json"})
    assert res.status_code == 409
    assert server.stats.rejected.get("expired_task") == 1


def test_solver_exception_does_not_kill_the_neuron():
    from fastapi.testclient import TestClient

    def explode(task):
        raise RuntimeError("boom")

    server = MinerServer(uid=0, name="broken", solver=explode, allow_unsigned=True)
    client = TestClient(build_miner_app(server))
    from subnet.transport.btauth import unsigned_headers

    task = TaskEngine(seed=1).generate(Category.MATH, 3).request
    res = client.post("/veritensor/v1/verify", content=task.model_dump_json(),
                      headers={**unsigned_headers("dev"),
                               "content-type": "application/json"})
    assert res.status_code == 500
    assert server.stats.rejected.get("solver_error") == 1
    assert client.get("/health").status_code == 200      # still alive


# ---------------------------------------------------------------- client
def test_client_rejects_a_response_bound_to_a_different_task():
    """A miner cannot answer task B with a response labelled task A."""
    import asyncio

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        async def post(self, *args, **kwargs):
            return FakeResponse({"task_id": "vt_other", "miner_uid": 0,
                                 "nonce": "0" * 32, "answer": "x",
                                 "confidence": 0.5, "execution_time_ms": 1})

    task = TaskEngine(seed=2).generate(Category.MATH, 3).request
    client = ValidatorClient(unsigned_identity="dev")
    response, error, _ = asyncio.run(
        client.query_one(FakeClient(), MinerEndpoint(uid=0, url="http://x"), task))
    assert response is None
    assert error == "task_binding_mismatch"
