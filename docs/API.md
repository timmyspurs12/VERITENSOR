# API reference

Base URL `http://localhost:8000`. Interactive documentation at `/api/docs`.

Common properties:

* All bodies are JSON. Request models set `extra="forbid"` — unknown fields are
  a 422, not a silent ignore.
* Every response carries `X-Request-Id`, `X-Response-Time-Ms` and the security
  headers listed in `docs/SECURITY.md`.
* Errors are `{"detail": "...", "request_id": "..."}`.
* Rate limits: 240 requests/minute per IP; 12/minute for `/api/simulation/*`
  and `/api/demo/*`. Exceeding them returns 429.
* Anything derived from the local engine is marked `synthetic: true`, and
  `mode_info.on_chain` states whether any figure came from a chain.

---

## System

### `GET /health`
`{"status": "ok", "mode": "LOCAL_SIMULATION"}`

### `GET /api/system/info`
Public settings, mode info and the boot report (how the seeded network was
produced). Never contains secrets.

### `GET /api/system/health`
Subnet status, per-validator liveness, miner health buckets, queue depth,
verification latency.

### `GET /api/chain/status`
Read-only Bittensor probe: SDK capabilities, chain reachability, subnet facts
and the per-prerequisite preflight. Performs chain **reads only** — it can
never sign or submit. Cached for 30 s; the payload carries `probed_at`,
`cached` and `age_seconds` so a stale reading cannot be mistaken for a live one.

```jsonc
{
  "sdk": {"installed": true, "version": "11.1.0", "generation": "supported",
          "http_auth": true, "set_weights": true, "legacy_synapse": false},
  "simulation_mode": true,
  "configured": {"netuid": 0, "network": "test", "wallet": false, "hotkey": false},
  "reachable": true,
  "ready_to_submit_weights": false,
  "preflight": {
    "block": 7873228,
    "subnet": {"name": "…", "num_uids": 56, "max_uids": 256, "tempo": 99},
    "registration_cost": "τ0.000500000",
    "checks": {"sdk_installed": true, "chain_reachable": true,
               "subnet_exists": true, "wallet_files_present": false,
               "hotkey_registered": false}
  }
}
```

### `GET /api/mechanism/config`
The live `MechanismConfig`: weights, latency budget, calibration policy,
evidence policy, robustness policy, reputation policy, penalties, emission
policy, difficulty thresholds.

---

## Network

### `GET /api/network/stats`
```jsonc
{
  "mode": "simulation", "netuid": 47,
  "active_miners": 16, "active_validators": 4,
  "tasks_verified": 260, "responses_evaluated": 3504,
  "network_accuracy": 0.707, "network_score": 0.643,
  "mean_latency_ms": 2048.2, "p95_latency_ms": 5574.0,
  "throughput_per_min": 684.6, "throughput_is_simulated": true,
  "robustness_probes": 1061, "robustness_hold_rate": 0.679,
  "rejected_responses": 0, "emission_gini": 0.302,
  "mode_info": { "on_chain": false, "synthetic_data": true, "...": "..." },
  "categories": [ { "category": "code", "tasks": 71, "accuracy": 0.72 } ],
  "config": { "weights": { "accuracy": 0.45 } }
}
```

### `GET /api/network/epochs?limit=40`
### `GET /api/network/graph`
`nodes` (validators + miners) and `edges` aggregated from the last 200 tasks:
`interactions`, `accuracy`, `mean_score` per validator↔miner pair.

---

## Miners

### `GET /api/miners?category=&limit=&offset=`
Leaderboard rows: rank, reputation, rolling/lifetime score, accuracy, task
count, mean latency, emission weight, trend, last-task components, per-category
stats, anti-gaming flags, archetype. With `category`, rows are ranked by mean
score in that family and gain `category_accuracy/score/tasks`.

### `GET /api/miners/{uid}`
Adds `history` (up to 200 snapshots), `emission_history`, `recent_tasks`
(with probe results), `failure_analysis`, `probe_outcomes`, `specialisation`.
404 for unknown uid.

### `POST /api/miners/register`  *(admin)*
`{"profile": "balanced", "name": "Optional-Name"}` → `201`.
Unknown profile → 422 listing valid archetypes.

### `POST /api/miners/{uid}/response`
Externally produced answer. The server verifies task binding and nonce and
grades the answer itself; the schema contains **no score-like field**, so a
client cannot assert its own quality. Returns 409 for tasks already closed by
their validator (all tasks in simulation mode), 422 on uid mismatch or an
out-of-range confidence.

### `GET /api/scores/{uid}?task_id=`
Score Explorer payload: component rows with `value × weight = contribution`,
subtotal, penalties, final score, formula, resulting reputation, EMA alpha and
emission weight.

---

## Validators

### `GET /api/validators`
### `POST /api/validators/evaluate`
`{"task_id": "vt_..."}` → the recorded consensus and per-miner evaluations.
Scores are never recomputed from client input.

---

## Tasks

### `GET /api/tasks`
Filters: `category`, `status`, `validator_uid`, `min_difficulty`,
`max_difficulty`, `limit` (≤100), `offset`. Returns `{total, limit, offset, items}`.

### `GET /api/tasks/{id}`
Full record: prompt, verification type, consensus, commitment, dropped miners
and every response with its score breakdown, penalties, flags and probe.
Contains `ground_truth_available: true` but **never** `ground_truth`.

### `GET /api/tasks/{id}/ground-truth`  *(admin)*
Hidden answer, explanation and commitment. Refuses tasks that are not closed.

### `POST /api/tasks`
`{"category": "code", "difficulty": 7, "validator_uid": 2}` — all optional.
Generates, dispatches, grades, probes, updates reputation and recomputes
emissions, then returns the closed task record. `201`.

---

## Emissions

### `GET /api/emissions`
Weight vector with `total_weight` (1.0 or 0.0), Gini, eligibility, exclusion
reasons per miner, per-miner weight history, the active emission policy and
epoch history.

---

## Simulation & demo

### `POST /api/simulation/run`
```json
{"miners": 25, "validators": 3, "tasks": 100, "difficulty": "adaptive", "seed": 42}
```
Bounds: miners ≤ 60, validators ≤ 7, tasks ≤ 400; `difficulty ∈
{easy, normal, hard, adaptive}`. Builds an isolated network and returns stats,
leaderboard, rank changes, emission before/after, epochs, adversarial summary,
category breakdown, health and the run's events. 429 if a simulation is
already running.

### `POST /api/demo/run`
Executes one task end to end and returns the eight pipeline stages, the task
(with ground truth revealed, because it is now closed), the updated
leaderboard, rank/emission movements and the events emitted during the run.

---

## Events

### `GET /api/events?limit=&after_seq=&kind=`
Monotonic `seq` supports incremental polling.

### `GET /api/events/stream`
`text/event-stream`; replays the last 20 events, then streams live with
15-second keep-alives.

Event kinds: `miner.registered`, `validator.registered`, `task.generated`,
`task.dispatched`, `miner.responded`, `miner.dropped`, `robustness.probe`,
`response.rejected`, `task.verified`, `emissions.updated`, `epoch.closed`.

---

## Admin

### `GET /api/admin/diagnostics`
Settings, boot report, stats, per-validator guard state, registered generators,
recent warnings/errors.

### `POST /api/admin/reset`
Rebuilds an empty network with the configured population.

Both require `X-Admin-Key` when `ADMIN_API_KEY` is set, and both 404 when debug
endpoints are disabled (always the case in production).
