# Architecture

## Layering

```
┌──────────────────────────────────────────────────────────────┐
│ frontend/  Next.js 14 · TypeScript · Tailwind · Recharts     │
│            13 routes, SWR polling + SSE, same-origin proxy   │
└───────────────▲──────────────────────────────────────────────┘
                │ HTTP (same origin, rewritten server-side)
┌───────────────┴──────────────────────────────────────────────┐
│ backend/   FastAPI · Pydantic · SQLAlchemy                   │
│  api/routes.py  → schemas/ → services/ → repositories/ → ORM │
│  core/: settings · structured logging · security middleware  │
└───────────────▲──────────────────────────────────────────────┘
                │ plain Python calls
┌───────────────┴──────────────────────────────────────────────┐
│ subnet/    protocol · tasks · miner · validator · scoring    │
│            adapters · simulation                             │
│            no web framework, no ORM, no chain dependency     │
└───────────────▲──────────────────────────────────────────────┘
                │ SubnetAdapter interface
        ┌───────┴────────┐
   SimulationAdapter   BittensorAdapter
   (in-process)        (bittensor SDK)
```

Dependencies point **inward only**. `subnet/` needs no web framework, ORM or
chain library to run.

## Neuron processes

A Bittensor subnet is two long-lived programs, not a web service. Both live in
`subnet/neurons/` and import only `subnet/`:

```
python -m subnet.neurons.miner     --config configs/miner.yaml
python -m subnet.neurons.validator --config configs/validator.yaml
```

```
validator neuron                              miner neuron
─────────────────                             ─────────────
task engine  (hidden truth + HMAC commit)
strategy → sample miners
btauth/1 sign  ───── POST /veritensor/v1/verify ─────▶ verify signature
                                                       receiver binding
                                                       clock skew + nonce replay
                                                       ↓
                                                       solver (heuristic |
                                                       profiled | model)
◀──────────── MinerResponse (answer, confidence, ──────
                              evidence, timing)
guard → score → probe → reputation
emission model → bittensor.set_weights (testnet only)
```

Transport is `subnet/transport/`, built on `bittensor.http_auth` (`btauth/1`) —
the protocol that replaced axon/dendrite in SDK v11. The backend and the
neurons are **peers over the same core**, not one inside the other.

## Request path — `POST /api/tasks`

```
route (Pydantic validation, extra="forbid")
  └─ SubnetService.run_task            async lock, asyncio.to_thread
       └─ SubnetNetwork.step
            └─ Validator.run_task
                 ├─ pipeline.generate        TaskEngine + guard.register_task
                 ├─ pipeline.dispatch        public TaskRequest only
                 ├─ pipeline.validate_response  replay / nonce / rate / deadline
                 ├─ pipeline.score_response  ScoringEngine → ScoreBreakdown
                 ├─ pipeline.robustness_probe  mutation, re-graded
                 ├─ pipeline.update_reputation EMA + trust ramp
                 └─ pipeline.consensus       observability only
       ├─ SubnetNetwork.recompute_emissions  normalise → cap → renormalise
       └─ SubnetService.persist              repository → session_scope
route returns TaskRecord.public_dict(reveal_truth=False)
```

Ground truth exists only inside `Validator.run_task` and the `TaskRecord`; the
serialiser that produces the HTTP response cannot emit it unless an
authenticated admin route sets `reveal_truth=True` on a closed task.

## Concurrency

* Task execution and simulations run in a worker thread
  (`asyncio.to_thread`) so the event loop keeps serving reads while the
  mechanism runs.
* An `asyncio.Lock` serialises mutations of the shared network, and a
  `_sim_running` flag rejects concurrent simulations with HTTP 429.
* The SSE endpoint attaches a bounded `asyncio.Queue` to the event bus and
  detaches on disconnect; a full queue drops the subscriber rather than
  blocking the producer.

## Data model

| Table | Purpose | Notable constraints |
| --- | --- | --- |
| `miners` | reputation snapshot per uid | `reputation ∈ [0,1]`, `emission_weight ∈ [0,1]`, `task_count ≥ 0`, unique uid |
| `validators` | strategy + counters | unique uid |
| `tasks` | executed tasks, hidden truth stored but never publicly projected | `difficulty ∈ [1,10]`, indexes on `(category,status)` and `created_at` |
| `responses` | graded responses | `score/confidence ∈ [0,1]`, `execution_time_ms ≥ 0`, `UNIQUE(task_id, miner_uid)` |
| `epochs` | epoch summary + weight vector | — |
| `events` | structured audit log | index on `seq` |

The runtime is authoritative during a session; the database is a durable
mirror written after each mutation.

## Frontend

* `app/` — 13 routes: landing, dashboard, live, graph, miners, miner profile,
  validators, tasks, task detail, scores, emissions, mechanism, simulation,
  demo, admin.
* `components/ui.tsx` — the design system (cards, badges, meters, tables,
  segmented controls, skeleton/empty/error states) built by hand rather than
  pulled from a template, so the visual language is consistent and the bundle
  stays small.
* `hooks/use-api.ts` — SWR hooks with sensible refresh intervals and
  `keepPreviousData` so numbers never flash empty.
* `hooks/use-event-stream.ts` — SSE with automatic polling fallback.
* `components/network-graph.tsx` — deterministic ring layout; edge opacity is
  real dispatch frequency, node size is real emission weight, illumination is
  driven by live events.

Every panel derives from an API response. There is no mock data module in the
frontend, and no component fabricates activity when the backend is idle — empty
states say so instead.
