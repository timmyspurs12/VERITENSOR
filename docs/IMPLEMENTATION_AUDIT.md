# Implementation audit

**Date:** 2026-08-27
**Auditor:** engineering pass prior to Bittensor Global Subnet Hackathon 2026 submission
**Repository state at audit:** local prototype, 127 python tests passing, 14 frontend routes,
no chain integration exercised.

This document records what existed *before* the testnet-readiness work, so that
the delta is auditable. Items fixed during that work are marked
`→ RESOLVED` with a pointer.

---

## 0. Executive summary

| Area | Verdict |
| --- | --- |
| Task engine, scoring, reputation, emissions | **Production-quality logic**, well tested, no changes required |
| Anti-gaming | Solid primitives, but **no adversarial test suite** proving they work |
| Backend API | Complete and validated; missing chain-status surface |
| Frontend | Complete; two-mode indicator only, no chainless-neuron mode |
| Bittensor adapter | **BROKEN — written against an SDK API that does not exist in the installed version** |
| Runnable neurons | **MISSING — the subnet could not run outside the FastAPI process** |
| Configs / scripts / evidence | **MISSING** |

The single most serious finding is the adapter: see §12.

---

## 1. Frontend architecture

**What exists.** Next.js 14 (app router), TypeScript strict, Tailwind with a
hand-built design system (`components/ui.tsx`), Recharts, lucide icons, SWR
hooks plus an SSE stream hook with polling fallback. 14 routes: landing,
dashboard, live, graph, miners, miner profile, validators, tasks, task detail,
scores, emissions, mechanism, simulation, demo, admin.

**Works.** All routes render against live API data; `tsc --noEmit` clean; 10
vitest tests covering formatters and mirrored mechanism arithmetic. No mock data
module exists in the frontend — empty states are shown when the backend is idle.

**Gap.** The mode banner models exactly two states (simulation / chain). Once
neurons can run as separate processes with real wallets but no chain, a third
state is needed, otherwise the UI would have to misreport one of them.
→ RESOLVED: three-state mode reporting, `components/mode-banner.tsx` +
`/api/chain/status`.

## 2. Backend architecture

**What exists.** FastAPI + Pydantic v2 + SQLAlchemy 2. Layering is clean:
`api/routes.py → schemas/ → services/subnet_service.py → repositories/ → models/`.
`core/` holds settings, JSON logging with request-id `ContextVar`, and security
middleware (rate limiting, headers, admin auth).

**Works.** 20+ endpoints, all request bodies `extra="forbid"`. Simulations run
in a worker thread under an asyncio lock. 34 API tests.

**Gap.** No endpoint exposed chain connectivity, so the frontend could not
distinguish "no chain configured" from "chain unreachable".
→ RESOLVED: `GET /api/chain/status`.

## 3. Database

SQLAlchemy models with real constraints: `CHECK` bounds on reputation/score/
confidence/difficulty, non-negative counters, `UNIQUE(task_id, miner_uid)`,
indexes on `(category, status)` and `created_at`. `session_scope()` commits or
rolls back. SQLite default, PostgreSQL via `DATABASE_URL`.

**Assessment.** Production-ready for the prototype's needs. The in-memory
runtime remains authoritative during a session; the DB is a durable mirror, not
an event-sourced log. Documented as a limitation, not a defect.

## 4. Task engine

13 generators across 4 families. Ground truth is *computed*, never hand-written:
output-prediction executes the reference implementation; reasoning tasks are
brute-force checked for solution uniqueness before publication; data tasks
inject known outliers. Deterministic verifiers with a registry
(`exact`, `boolean`, `numeric`, `set_match`, `sequence`, `multiple_choice`,
`python_predicate` with AST validation).

**Assessment.** The strongest part of the codebase. No changes required.

## 5. Miner simulator

9 behavioural archetypes with independent accuracy curves, latency
distributions, confidence bias, evidence quality, robustness decay and dropout.
Simulation-only knowledge is isolated in `subnet/miner/oracle.py`.

**Gap.** `ModelMiner` existed as the "production shape" but nothing could
actually *serve* it: there was no network listener, no request authentication,
no CLI.
→ RESOLVED: `subnet/neurons/miner.py` + `subnet/transport/`.

## 6. Validator simulator

`Validator.run_task` orchestrates independently testable pipeline stages.
6 strategies. Own task engine, guard and scorer per validator.

**Gap.** Same as §5 — in-process only, no dispatch over a wire, no weight
submission path.
→ RESOLVED: `subnet/neurons/validator.py`.

## 7. Scoring engine

Weighted 45/20/15/10/10 from `MechanismConfig`; all components clamped to
`[0,1]` with NaN/inf mapped to the floor; penalties multiplicative and capped.

**Gaps found.**
* No explicit **outlier protection** — a single anomalous latency or a
  pathological response could skew a component.
* Malformed miner responses were rejected by Pydantic at the edge but there was
  no defined in-pipeline behaviour for a *structurally valid but semantically
  junk* response (e.g. 16 kB of whitespace).
→ RESOLVED: `subnet/scoring/components.py` winsorised latency + junk-response
guard; tests in `tests/test_scoring.py`.

## 8. Reputation system

EMA (α=0.15) with a trust ramp (`min(1, tasks/20)`) toward a low prior; per
category stats; bounded 500-snapshot history; emission history.

**Assessment.** Correct and tested (`one lucky task` test). No change required.

## 9. Emission system

Eligibility filter → floor subtraction → temperature sharpening → normalisation
→ per-miner cap (relaxed to `2/n` in small networks) → renormalisation with
residual assignment. `weights_to_bittensor()` produced `(uids, u16)`.

**Gap.** The u16 conversion targeted the *old* SDK signature. The installed SDK
takes a `{uid: float}` mapping and quantises internally.
→ RESOLVED: `weights_to_uid_map()` added; u16 helper retained for older SDKs and
documented as such.

## 10. API

Covered in §2. Ground truth is structurally excluded from public projections
(`PUBLIC_TASK_COLUMNS`, `public_dict(reveal_truth=False)`), with a regression
test.

## 11. Tests

127 python tests over 7 modules + 10 vitest tests.

**Gaps.**
* No **single integration test** exercising the whole pipeline at the required
  scale (10 miners / 3 validators / 100 tasks) and asserting archetype
  differentiation.
* No **adversarial suite** simulating attacker behaviour end to end.
* No tests for transport, neuron configuration, or the adapter against the real
  SDK.
→ RESOLVED: `tests/test_pipeline_integration.py`, `tests/test_adversarial.py`,
`tests/test_transport.py`, `tests/test_neurons.py`, `tests/test_chain_adapter.py`.

## 12. Bittensor adapter — **critical finding**

The adapter was written against Bittensor SDK v8/v9 conventions:

```python
bt.Subtensor(network=...)          # class, capitalised
subtensor.metagraph(netuid=...)    # method on the client
subtensor.set_weights(wallet=..., netuid=..., uids=[...], weights=[...])
bt.Dendrite(wallet=...).query(axons=..., synapse=...)
class VerificationSynapse(bt.Synapse): ...
bt.Axon
```

The SDK actually installed is **bittensor 11.1.0**, in which:

| Old API | Status in 11.1.0 |
| --- | --- |
| `bt.Synapse` | **does not exist** |
| `bt.Axon` / `bt.axon` | **does not exist** |
| `bt.Dendrite` / `bt.dendrite` | **does not exist** |
| `bt.Subtensor(network=)` | exists as `bt.subtensor(network)` (also `bt.Subtensor`) |
| `subtensor.metagraph(netuid)` | now `client.subnets.metagraph(netuid=...)` |
| `subtensor.set_weights(wallet, netuid, uids, weights)` | now module-level `bt.set_weights(netuid, {uid: w}, wallet=, hotkey=, network=)` |
| `subtensor.burned_register(...)` | now intent `bt.BurnedRegister(netuid, hotkey_ss58)` executed via `client.execute(intent, wallet)` |

Every adapter method would therefore have raised `AttributeError` the moment a
wallet was configured. The adapter's honesty guard (`AdapterUnavailable` when
unconfigured) masked this: it never ran, so it never failed visibly.

**The axon/dendrite/Synapse pattern is gone.** v11 replaces it with
`bt.http_auth`, a normative signed-HTTP protocol (`btauth/1`): the caller signs
`(protocol, scheme, method, path, sha256(body), nonce_ns, sender, receiver)`
with its hotkey; the server verifies signature, receiver binding, clock skew and
nonce replay. Subnets implement their own HTTP servers on top of it.

→ RESOLVED: adapter rewritten against the verified 11.x surface
(`subnet/adapters/bittensor_adapter.py`), transport implemented on
`bt.http_auth` (`subnet/transport/`), and a capability probe added
(`subnet/chain/sdk.py`) so a version mismatch is reported rather than
discovered at runtime.

**Verification performed during this audit** (all offline, no chain writes):

```
bittensor 11.1.0 imported
wallet created locally (throwaway path)      → coldkey + hotkey sr25519
bt.http_auth.sign / verify round trip        → PASS
tampered body                                → BadSignature raised
replayed nonce                               → ReplayedRequest raised
bt.subtensor("test").block                   → 7872987   (read-only)
client.subnets.metagraph(netuid=1)           → "apex", 256 uids, 129 validators
client.read("burn", netuid=1)                → τ0.0005
```

Chain **reads** work from this environment. Chain **writes** (registration,
weight submission) require a funded, registered hotkey — see
`docs/DEPLOYMENT_CHECKLIST.md`.

## 13. Docker configuration

`Dockerfile.backend` (non-root, healthcheck), `Dockerfile.frontend`
(multi-stage), `docker-compose.yml` with PostgreSQL 16 + healthcheck gating.

**Gap.** No service definition for standalone miner/validator neurons, and the
Bittensor SDK was not installed in the backend image.
→ RESOLVED: `requirements-bittensor.txt`, optional `miner`/`validator` compose
profiles.

**Note.** Docker is not available inside the development sandbox, so the images
are **config-reviewed, not build-verified**. Stated as such in
`docs/FINAL_READINESS_REPORT.md` rather than claimed as passing.

## 14. Environment configuration

`.env.example` covered runtime, DB, subnet, seeding, security and model backend.

**Gaps.** No axon host/port, no external miner endpoints, no wallet path, no
chainless-neuron mode flag, and no YAML configs for neuron processes.
→ RESOLVED: extended `.env.example`, added `configs/miner.yaml`,
`configs/validator.yaml`, `configs/testnet.yaml`.

## 15. Documentation

README (552 lines) plus MECHANISM, ANTI_GAMING, SECURITY, LIMITATIONS,
ARCHITECTURE, API, TESTNET.

**Gaps.** TESTNET.md described the *old* SDK. No hackathon submission document,
no deployment checklist, no evidence protocol, no readiness report.
→ RESOLVED: TESTNET.md rewritten for 11.x; added HACKATHON_SUBMISSION,
DEPLOYMENT_CHECKLIST, TESTNET_EVIDENCE, FINAL_READINESS_REPORT, SCORING,
IMPLEMENTATION_AUDIT (this file).

---

## Architectural problems that had to be fixed

1. **Adapter written against a non-existent API** (§12) — the only true
   correctness bug found. Fixed and now covered by tests that run against the
   installed SDK.
2. **The subnet could not run outside the web process.** A Bittensor subnet is
   two long-lived neuron programs; the mechanism being callable only from a
   FastAPI service was a structural blocker to any real deployment. Fixed by
   `subnet/neurons/`, which depends on `subnet/` only — the backend and the
   neurons are now peers over the same core, not one inside the other.
3. **No evidence trail.** Nothing recorded what actually happened during a run,
   so no claim about behaviour was independently checkable. Fixed by
   `subnet/evidence.py` writing timestamped JSONL under `evidence/`.

## Explicitly NOT changed

The task engine, scoring maths, reputation model, emission model, database
schema, API contract and frontend design were left intact. They were audited,
found sound, and rewriting them would have added risk without adding
capability.
