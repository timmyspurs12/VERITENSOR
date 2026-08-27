# VERITENSOR

**The decentralized verification layer for machine intelligence.**

> Miners compete to produce reliable AI answers. Validators independently verify
> them. Performance determines reputation and emission.

A Bittensor subnet prototype built for the **Bittensor Global Subnet Hackathon
2026**. VERITENSOR does not reward miners for producing AI output — it rewards
output that **survives independent verification**.

**Deployment status: not deployed to a Bittensor subnet.** No hotkey is
registered and no weight has been submitted on chain. What runs today is the
complete mechanism, plus two standalone neuron programs that talk over the
Bittensor SDK's own signed-HTTP protocol with real wallets. Everything
outstanding is enumerated in [`docs/DEPLOYMENT_CHECKLIST.md`](docs/DEPLOYMENT_CHECKLIST.md).

| | |
| --- | --- |
| Tests | 211 Python + 10 frontend, all passing |
| Task generators | 13 across 4 verifiable families + an 18-item private bank |
| Adversarial suite | 29 attacks, measured in [`docs/attack_report.json`](docs/attack_report.json) |
| SDK | bittensor **11.1.0**, verified — uses `http_auth`, `subtensor`, `set_weights` |
| Modes | `simulation` · `local_neurons` · `bittensor_testnet` |

---

## Contents

1. [Problem](#1-problem) · 2. [Solution](#2-solution) · 3. [Architecture](#3-architecture)
4. [Mechanism](#4-mechanism) · 5. [Miner](#5-miner) · 6. [Validator](#6-validator)
7. [Scoring](#7-scoring) · 8. [Anti-gaming](#8-anti-gaming) · 9. [Local simulation](#9-local-simulation)
10. [Testnet setup](#10-testnet-setup) · 11. [Environment variables](#11-environment-variables)
12. [Running a miner](#12-running-a-miner) · 13. [Running a validator](#13-running-a-validator)
14. [Running tests](#14-running-tests) · 15. [Running the frontend](#15-running-the-frontend)
16. [Evidence](#16-evidence) · 17. [Limitations](#17-limitations) · 18. [Roadmap](#18-roadmap)

---

## 1. Problem

Machine-generated answers are abundant and nearly free. Knowing which of them
are *correct* is neither.

* **Verification does not scale.** It still costs a human or a deterministic
  checker, and demand has grown orders of magnitude faster than supply.
* **Static benchmarks decay into answer keys.** Once public, a benchmark
  measures memorisation.
* **Confidence is unpriced.** Being right 60% of the time while claiming 95%
  certainty is worse than admitting doubt, and nothing charges for it.
* **Robustness is untested.** An answer that flips when a variable is renamed
  was never knowledge.

## 2. Solution

A validator generates a task whose answer it already knows but has never
published, and commits to that answer before dispatch. Miners answer over
authenticated transport. The validator grades five dimensions, probes
robustness with a semantics-preserving mutation, and converts the result into a
normalised emission weight.

```
TASK → MINERS → ANSWERS → VALIDATORS → VERIFICATION → REPUTATION → EMISSIONS → BETTER MINERS
```

## 3. Architecture

```
                    ┌───────────────────────────────────────────────┐
                    │  frontend/   Next.js 14 · TS · Tailwind       │
                    │  15 routes · SSE stream · 3-state mode banner │
                    └───────────────────▲───────────────────────────┘
                                        │ same-origin HTTP (proxied)
                    ┌───────────────────┴───────────────────────────┐
                    │  backend/    FastAPI · Pydantic · SQLAlchemy  │
                    │  routes → schemas → services → repositories   │
                    └───────────────────▲───────────────────────────┘
                                        │ plain Python
┌───────────────────────────────────────┴───────────────────────────────────┐
│  subnet/    protocol · tasks · miner · validator · scoring · transport     │
│             chain · adapters · simulation · evidence                       │
│             (no web framework, no ORM, no chain coupling)                  │
└───────▲───────────────────────────────────────────────────────▲───────────┘
        │ SubnetAdapter                                          │ btauth/1
 ┌──────┴─────────┐  ┌──────────────────┐        ┌──────────────┴──────────┐
 │ SimulationAdapter │ BittensorAdapter │        │ neuron processes        │
 │ (in-process)      │ (SDK 11 · chain) │        │ miner ⇄ validator       │
 └───────────────────┴──────────────────┘        └─────────────────────────┘
```

```
veritensor/
├── subnet/                     # the subnet itself — importable, runnable, standalone
│   ├── protocol/               # wire types, CSPRNG ids/nonces, HMAC commitments
│   ├── tasks/                  # 13 generators, mutation engine, verifiers
│   ├── miner/                  # solvers (real), archetypes, model backends
│   ├── validator/              # pipeline stages, strategies, event bus
│   ├── scoring/                # weights, calibration, reputation, emissions, anti-gaming
│   ├── transport/              # btauth/1 signed HTTP client + server
│   ├── chain/                  # SDK capability probe, wallet helpers
│   ├── adapters/               # SubnetAdapter: simulation | bittensor
│   ├── neurons/                # runnable miner + validator programs, YAML config
│   ├── simulation/             # in-process network runtime
│   └── evidence.py             # timestamped JSONL evidence recorder
├── backend/  frontend/  benchmarks/  tests/  docs/  configs/  scripts/
└── docker-compose.yml · Dockerfile.backend · Dockerfile.frontend · .env.example
```

Dependencies point inward only: `subnet/` knows nothing about FastAPI,
SQLAlchemy or the frontend.

## 4. Mechanism

| Stage | Implementation |
| --- | --- |
| Task generation | 13 seeded generators; ground truth computed, never written |
| Commitment | `HMAC(secret, task_id ‖ nonce ‖ answer)` published before dispatch |
| Dispatch | btauth/1 signed HTTP, bound to the receiving miner's hotkey |
| Validation | schema, task binding, nonce, deadline, rate, duplicates |
| Scoring | accuracy 45 · evidence 20 · robustness 15 · calibration 10 · latency 10 |
| Robustness | semantics-preserving mutation probe after a correct answer |
| Reputation | EMA α=0.15 with a 20-task trust ramp and outlier clamping |
| Emissions | eligibility → floor → temperature 2.5 → normalise → cap → renormalise |

Full derivations: [`docs/SCORING.md`](docs/SCORING.md) ·
[`docs/MECHANISM.md`](docs/MECHANISM.md)

## 5. Miner

A miner receives only a `TaskRequest` — no ground truth exists in the type:

```json
{"task_id":"vt_9f2c…","category":"code","difficulty":8,
 "prompt":"Analyse the following Python snippet…","nonce":"6b1f…",
 "deadline":"2026-08-27T09:14:31Z","verification_type":"programmatic"}
```

and returns a `MinerResponse` echoing the nonce (the replay binding):

```json
{"task_id":"vt_9f2c…","miner_uid":3,"nonce":"6b1f…","answer":"VULNERABLE",
 "confidence":0.91,"evidence":[{"kind":"reasoning","content":"SQL built by string…"}],
 "execution_time_ms":1180,"model_metadata":{"backend":"heuristic"}}
```

Three solver backends:

| Backend | What it is |
| --- | --- |
| `heuristic` | a **real** solver: executes code, does modular arithmetic, runs constraint search, computes statistics. ~99% on the generated pool. |
| `profiled` | the heuristic solver degraded by an archetype (latency, error rate, confidence bias, evidence quality) so a local topology has distinguishable operators |
| `model` | any OpenAI-compatible endpoint via `ModelBackend`; key read from the environment, never logged |

## 6. Validator

Each validator owns an independent task engine, anti-gaming guard and scorer.
Six strategies vary coverage, probe rate and category mix, so a miner cannot
overfit to one grader. Log output is produced from real values only:

```
[VERITENSOR VALIDATOR]

Task: vt_737125a6afb986c1
Category: REASONING
Difficulty: 3

Miners queried: 10
Responses received: 10

Accuracy: 0.700
Evidence: 0.508
Robustness: 0.706
Calibration: 0.543
Latency: 0.899

Final score:
  miner-09 = 0.885  ✓
  miner-01 = 0.880  ✓  probe:held
  miner-07 = 0.073  ✕

Weight update:
  miner-09 = 0.188
  miner-01 = 0.185
```

## 7. Scoring

```
final = (accuracy·0.45 + evidence·0.20 + robustness·0.15
         + calibration·0.10 + latency·0.10) · (1 − penalties)
```

Weights live in one configuration object and are validated to sum to 1.0.
Calibration is a Brier score over a 50-response window: 0.95 confidence at 60%
accuracy scores **0.000**. Latency is a budget (full marks under 1200 ms),
never a race. Emissions always sum to exactly 1.0.

## 8. Anti-gaming

Measured against the real pipeline by `tests/test_adversarial.py`:

| Attack | Outcome |
| --- | --- |
| Prompt memorisation | 0.75% reuse over 400 draws |
| Constant-answer farming | 0% emission, flagged |
| Confidence inflation | calibration 0.000 |
| Cross-task replay / duplicate submit | rejected pre-scoring |
| 100 sybils, one perfect task each | 0% of emissions |
| Hostile majority (6 of 10) | honest miners take 89.2% |

Details, assumptions and honest gaps: [`docs/ANTI_GAMING.md`](docs/ANTI_GAMING.md)

## 9. Local simulation

```bash
pip install -r requirements-dev.txt

# headless, prints the leaderboard it just produced
python -m scripts.run_simulation --miners 50 --validators 5 --tasks 100

# or the full stack (dashboard + API)
uvicorn backend.main:app --reload --port 8000     # seeds ~260 tasks on boot
cd frontend && npm install && npm run dev         # http://localhost:3000
```

## 10. Testnet setup

Read-only preflight first — it never signs or submits:

```bash
python -m scripts.preflight --netuid <NETUID> --network test
```

Then the operator steps (these involve keys and money, and are deliberately not
automated):

```bash
btcli wallet new_coldkey --wallet.name veritensor
btcli wallet new_hotkey  --wallet.name veritensor --wallet.hotkey miner-00
btcli wallet faucet      --wallet.name veritensor --subtensor.network test
btcli subnet list        --subtensor.network test
btcli subnet register --netuid <NETUID> --wallet.name veritensor \
      --wallet.hotkey miner-00 --subtensor.network test        # burns TAO
```

Full sequence: [`docs/DEPLOYMENT_CHECKLIST.md`](docs/DEPLOYMENT_CHECKLIST.md) ·
SDK details: [`docs/TESTNET.md`](docs/TESTNET.md)

## 11. Environment variables

Copy `.env.example` to `.env`. Never commit a real `.env`.

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | `development` \| `staging` \| `production` \| `test` |
| `SIMULATION_MODE` | `true` = SimulationAdapter, `false` = BittensorAdapter |
| `DATABASE_URL` | SQLite by default; PostgreSQL for a real deployment |
| `SUBNET_NETUID` | **0 until a hotkey is registered** — a real value implies deployment |
| `SIMULATION_NETUID` | display-only id for the local subnet (never sent to a chain) |
| `BITTENSOR_NETWORK` | `test` \| `finney` \| `ws://…` |
| `BITTENSOR_WALLET_NAME` / `_HOTKEY_NAME` / `_WALLET_PATH` | wallet *names* only; keys stay in `~/.bittensor` |
| `VERITENSOR_MODE` | `simulation` \| `local_neurons` \| `bittensor_testnet` |
| `VERITENSOR_AXON_HOST` / `_PORT` / `_EXTERNAL_IP` | miner axon binding and advertised address |
| `VERITENSOR_EVIDENCE_DIR` | where evidence runs are written |
| `ADMIN_API_KEY` | guards `/api/admin/*` and ground-truth reveal |
| `MODEL_API_KEY` / `MODEL_BASE_URL` | optional model backend; never sent to the browser |
| `VERITENSOR_COMMIT_SECRET` | HMAC key for ground-truth commitments |

## 12. Running a miner

```bash
# local, unfunded dev wallets, signed transport
./scripts/setup_testnet.sh
python -m subnet.neurons.miner --config configs/miner.yaml --uid 0 --axon.port 9100

# ten miners at once (ports 9100–9109, one archetype each)
# needs ~1 GB free RAM; the script checks first and refuses with advice
# rather than hanging. Scale down with VT_MINERS=4 on a small host.
./scripts/start_miners.sh

# inspect the resolved configuration without starting anything
python -m subnet.neurons.miner --config configs/miner.yaml --print-config

# on testnet (after registration)
VT_MODE=bittensor_testnet ./scripts/start_miners.sh
```

Check it is genuinely authenticated:

```bash
curl -s localhost:9100/health | jq
# {"transport":"btauth/1","signed_transport":true,"hotkey_ss58":"5Cho…"}

curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:9100/veritensor/v1/verify -d '{}'
# 401
```

## 13. Running a validator

```bash
# against local miners, 15 rounds then exit
python -m subnet.neurons.validator --config configs/validator.yaml --rounds 15

# three validators with different strategies
VT_ROUNDS=15 ./scripts/start_validators.sh

# on testnet: metagraph discovery + on-chain weight submission
python -m subnet.neurons.validator --config configs/testnet.yaml \
       --netuid <NETUID> --network test --submit-weights --rounds 20

./scripts/stop_all.sh
```

## 14. Running tests

```bash
pytest -q                                   # 211 tests
pytest tests/test_pipeline_integration.py -v  # 10 miners × 3 validators × 100 tasks
pytest tests/test_adversarial.py -q           # 29 attacks → docs/attack_report.json
pytest tests/test_transport.py -q             # btauth/1 against the installed SDK
VERITENSOR_SKIP_NETWORK_TESTS=1 pytest -q     # offline

cd frontend && npx vitest run && ./node_modules/.bin/tsc --noEmit
```

## 15. Running the frontend

```bash
cd frontend && npm install && npm run dev     # http://localhost:3000
```

The banner states `LOCAL SIMULATION`, `LOCAL NEURONS` or `BITTENSOR TESTNET`
based on what the backend adapter is actually doing, and the dashboard carries
a read-only chain panel listing genuinely unmet prerequisites.

Docker:

```bash
docker compose up --build                     # postgres + backend + frontend
docker compose --profile neurons up --build   # standalone miner + validator
```

## 16. Evidence

Every neuron run writes timestamped JSONL under `evidence/<run_id>/` — queries,
responses, scores, weights, metrics — each line tagged with its mode and an
explicit `on_chain` flag.

```bash
jq -c '{total, submitted, on_chain, reason}' evidence/*validator*/weights/weights.jsonl
```

Protocol and reproduction steps: [`docs/TESTNET_EVIDENCE.md`](docs/TESTNET_EVIDENCE.md)

## 17. Limitations

* **Not deployed on a Bittensor subnet.** Reads are verified against the live
  test network; registration and weight submission need a funded coldkey.
* Miner archetypes degrade a genuinely computed answer — a model of operator
  quality, not evidence about any AI system.
* Evidence scoring is lexical and gameable by subtle padding.
* Collusion detection catches byte-identical evidence only.
* Rate limiting is in-process.
* The ground-truth commitment is not yet published on chain.
* Docker images are config-reviewed, not build-verified (no Docker in the
  development sandbox).

Full list: [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) ·
Readiness split: [`docs/FINAL_READINESS_REPORT.md`](docs/FINAL_READINESS_REPORT.md)

## 18. Roadmap

| Horizon | Item |
| --- | --- |
| Now | Local subnet + distributed neurons over signed transport |
| Next | Register 10 miner + 3 validator hotkeys on testnet; publish weights |
| Then | On-chain commit–reveal for externally auditable grading |
| Then | Real model miners competing against the heuristic baseline |
| Later | Entailment-based evidence scoring |
| Later | Verification marketplace for external clients |

---

### Documentation

[Hackathon submission](docs/HACKATHON_SUBMISSION.md) ·
[Implementation audit](docs/IMPLEMENTATION_AUDIT.md) ·
[Architecture](docs/ARCHITECTURE.md) ·
[Scoring](docs/SCORING.md) ·
[Mechanism](docs/MECHANISM.md) ·
[Anti-gaming](docs/ANTI_GAMING.md) ·
[Security](docs/SECURITY.md) ·
[API](docs/API.md) ·
[Testnet](docs/TESTNET.md) ·
[Evidence](docs/TESTNET_EVIDENCE.md) ·
[Deployment checklist](docs/DEPLOYMENT_CHECKLIST.md) ·
[Readiness report](docs/FINAL_READINESS_REPORT.md) ·
[Limitations](docs/LIMITATIONS.md)

*Independent hackathon project. Not affiliated with, sponsored by, or endorsed
by the Opentensor Foundation. All demonstration data is generated locally and
labelled as such in the API and the UI.*
