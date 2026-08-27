"""API contract, validation and security tests."""

import pytest


def test_health_and_mode(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "LOCAL_SIMULATION"


def test_stats_are_real_and_labelled(api_client):
    data = api_client.get("/api/network/stats").json()
    assert data["tasks_verified"] > 0
    assert data["mode_info"]["on_chain"] is False
    assert data["mode_info"]["synthetic_data"] is True
    assert 0.0 <= data["network_accuracy"] <= 1.0
    assert sum(c["tasks"] for c in data["categories"]) == data["tasks_verified"]


def test_security_headers_and_request_id(api_client):
    r = api_client.get("/api/network/stats")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["x-request-id"]


def test_miners_pagination_and_ordering(api_client):
    data = api_client.get("/api/miners?limit=5").json()
    assert len(data["items"]) == 5
    reps = [m["reputation"] for m in data["items"]]
    assert reps == sorted(reps, reverse=True)
    assert data["total"] >= 5


def test_miner_detail_contains_history(api_client):
    uid = api_client.get("/api/miners?limit=1").json()["items"][0]["uid"]
    detail = api_client.get(f"/api/miners/{uid}").json()
    assert detail["history"] and detail["recent_tasks"]
    assert detail["synthetic"] is True
    assert "profile_label" in detail


def test_unknown_miner_returns_404(api_client):
    assert api_client.get("/api/miners/99999").status_code == 404


def test_score_explanation_arithmetic_is_consistent(api_client):
    uid = api_client.get("/api/miners?limit=1").json()["items"][0]["uid"]
    data = api_client.get(f"/api/scores/{uid}").json()
    subtotal = sum(r["contribution"] for r in data["rows"])
    assert subtotal == pytest.approx(data["subtotal"], abs=1e-6)
    expected = data["subtotal"] * (1 - data["penalty_total"])
    assert expected == pytest.approx(data["final_score"], abs=1e-6)
    assert sum(r["weight"] for r in data["rows"]) == pytest.approx(1.0, abs=1e-9)


# ------------------------------------------------------------- ground truth
def test_ground_truth_never_leaks_through_task_apis(api_client):
    listing = api_client.get("/api/tasks?limit=25").json()
    assert "ground_truth" not in str(listing)
    for item in listing["items"][:10]:
        detail = api_client.get(f"/api/tasks/{item['task_id']}").json()
        assert "ground_truth" not in detail
        assert detail["ground_truth_available"] is True


def test_ground_truth_available_to_admin_for_closed_tasks(api_client):
    task_id = api_client.get("/api/tasks?limit=1").json()["items"][0]["task_id"]
    r = api_client.get(f"/api/tasks/{task_id}/ground-truth")
    assert r.status_code == 200
    assert r.json()["ground_truth"]
    assert r.json()["commitment"]


# ------------------------------------------------------------- validation
@pytest.mark.parametrize("payload", [
    {"miners": 0}, {"miners": 10_000}, {"tasks": -5}, {"validators": 99},
    {"difficulty": "impossible"}, {"seed": -1}, {"unexpected_field": 1},
])
def test_simulation_rejects_invalid_payloads(api_client, payload):
    assert api_client.post("/api/simulation/run", json=payload).status_code == 422


@pytest.mark.parametrize("payload", [
    {"category": "sports"}, {"difficulty": 0}, {"difficulty": 11},
    {"validator_uid": -1}, {"score": 1.0},
])
def test_task_creation_rejects_invalid_payloads(api_client, payload):
    assert api_client.post("/api/tasks", json=payload).status_code == 422


def test_client_cannot_inject_scores(api_client):
    """Score-like fields are not part of any request schema."""
    r = api_client.post("/api/tasks", json={"category": "math", "score": 1.0,
                                            "reputation": 1.0})
    assert r.status_code == 422


def test_response_submission_cannot_target_a_closed_task(api_client):
    task_id = api_client.get("/api/tasks?limit=1").json()["items"][0]["task_id"]
    r = api_client.post("/api/miners/0/response", json={
        "task_id": task_id, "miner_uid": 0, "nonce": "a" * 32,
        "answer": "42", "confidence": 1.0, "execution_time_ms": 1})
    assert r.status_code == 409


def test_response_submission_rejects_uid_mismatch(api_client):
    r = api_client.post("/api/miners/1/response", json={
        "task_id": "vt_deadbeef", "miner_uid": 2, "nonce": "a" * 32,
        "answer": "42", "confidence": 0.5, "execution_time_ms": 1})
    assert r.status_code == 422


def test_confidence_out_of_range_is_rejected(api_client):
    r = api_client.post("/api/miners/1/response", json={
        "task_id": "vt_deadbeef", "miner_uid": 1, "nonce": "a" * 32,
        "answer": "42", "confidence": 5.0, "execution_time_ms": 1})
    assert r.status_code == 422


# ------------------------------------------------------------- pipeline
def test_create_task_executes_full_pipeline(api_client):
    r = api_client.post("/api/tasks", json={"category": "math", "difficulty": 4})
    assert r.status_code == 201
    task = r.json()
    assert task["status"] == "scored"
    assert task["responses"]
    assert "ground_truth" not in task
    assert task["consensus"]["verification_confidence"] >= 0


def test_emissions_sum_to_one(api_client):
    data = api_client.get("/api/emissions").json()
    assert data["total_weight"] == pytest.approx(1.0, abs=1e-6)
    assert all(0 <= item["emission_weight"] <= 1 for item in data["items"])


def test_simulation_endpoint_returns_real_results(api_client):
    r = api_client.post("/api/simulation/run",
                        json={"miners": 8, "validators": 2, "tasks": 20,
                              "difficulty": "normal", "seed": 5})
    assert r.status_code == 200
    data = r.json()
    assert data["tasks_completed"] == 20
    assert len(data["leaderboard"]) == 8
    assert data["adversarial"]["probes"] >= 0
    assert data["mode_info"]["on_chain"] is False


def test_demo_runs_all_stages(api_client):
    data = api_client.post("/api/demo/run").json()
    assert [s["stage"] for s in data["stages"]] == [
        "generate", "dispatch", "responses", "verify", "robustness", "score",
        "reputation", "emissions"]
    assert data["task"]["responses"]
    assert data["movements"]


def test_events_endpoint_is_incremental(api_client):
    first = api_client.get("/api/events?limit=5").json()
    assert first
    last_seq = first[-1]["seq"]
    later = api_client.get(f"/api/events?limit=5&after_seq={last_seq}").json()
    assert all(e["seq"] > last_seq for e in later)


def test_graph_edges_reference_existing_nodes(api_client):
    data = api_client.get("/api/network/graph").json()
    ids = {n["id"] for n in data["nodes"]}
    for edge in data["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_validators_endpoint(api_client):
    data = api_client.get("/api/validators").json()
    assert data and all("strategy" in v for v in data)


def test_mechanism_config_exposes_weights(api_client):
    cfg = api_client.get("/api/mechanism/config").json()
    assert sum(cfg["weights"].values()) == pytest.approx(1.0)


def test_admin_diagnostics_available_outside_production(api_client):
    r = api_client.get("/api/admin/diagnostics")
    assert r.status_code == 200
    assert "guards" in r.json()
