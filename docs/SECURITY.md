# Security considerations

## Secrets
* All credentials are read from the environment. `.env.example` contains
  placeholders only, and `tests/test_security.py::test_no_secrets_in_repository`
  scans the tree for key-shaped strings.
* `Settings.public_dict()` returns booleans such as
  `model_backend_configured`, never values — regression-tested.
* `OpenAICompatibleBackend.__repr__` masks the API key so it cannot appear in a
  traceback or log line.
* No key or backend URL is shipped to the browser: the frontend calls
  same-origin paths that Next rewrites to the backend server-side.

## Authentication and authorisation
* Admin routes (`/api/admin/*`, `/api/miners/register`,
  `/api/tasks/{id}/ground-truth`) depend on `require_admin`, which compares
  `X-Admin-Key` with `hmac.compare_digest`.
* With no key configured: allowed in development, **503 in production**. Never
  silently open.
* `ENABLE_DEBUG_ENDPOINTS` is forced off when `ENVIRONMENT=production`.

## Input validation
* Every request body is a Pydantic model with `extra="forbid"` and bounded
  fields, so `{"score": 1.0}` is rejected with 422 rather than ignored.
* Query parameters are bounded (`limit ≤ 100`, `difficulty ∈ [1,10]`, …).
* Simulation parameters are clamped server-side irrespective of the request.
* The sandboxed `python_predicate` verifier AST-validates expressions: no
  imports, no lambdas/comprehensions, no attribute access outside `math`, calls
  restricted to an allowlist, no dunder names. Predicates are validator-authored
  in any case; this is defence in depth.

## Transport and headers
* CORS allowlist from `CORS_ORIGINS`; a wildcard origin raises in production.
* Every response carries `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy` and a restrictive CSP.
* Request IDs are generated per request, echoed in `X-Request-Id` and bound to
  a `ContextVar` so every structured log line is correlatable.

## Rate limiting
* `RateLimitMiddleware`: per-IP fixed window, 240 rpm default, 12 rpm for
  `/api/simulation/*` and `/api/demo/*`.
* `AntiGamingGuard`: per-miner token bucket at the protocol layer.
* **Limitation:** both are in-process. A multi-worker or multi-replica
  deployment must front them with a shared limiter.

## Data protection
* Hidden ground truth is structurally excluded from public projections:
  `TaskRecord.public_dict(reveal_truth=False)` and
  `PUBLIC_TASK_COLUMNS` in the repository never select it.
* `reveal_ground_truth()` refuses tasks that are not `scored`/`verified`.
* `tests/test_api.py::test_ground_truth_never_leaks_through_task_apis` asserts
  the substring is absent from list and detail responses.

## Database
* `CHECK` constraints bound reputation, score and confidence to `[0,1]`,
  difficulty to `[1,10]`, and forbid negative counters and latencies.
* `UNIQUE(task_id, miner_uid)` makes double submission impossible at the
  storage layer as well as the protocol layer.
* `session_scope()` commits on success and rolls back on any exception.
* Persistence failures are logged and swallowed so a storage problem degrades
  history rather than taking the subnet down.

## Errors and logging
* A global exception handler returns `{"detail": "internal error", "request_id"}`
  — no stack traces or internal paths reach the client.
* Logs are JSON with a stable schema; task creation, scoring, emission updates,
  registrations and simulations are emitted as structured audit events.

## Not implemented (deliberately)
* User accounts/sessions — the prototype has no end-user identity model.
* mTLS between miner and validator — Bittensor's axon/dendrite layer owns that
  in a real deployment.
* On-chain commitment publication — see the roadmap.
