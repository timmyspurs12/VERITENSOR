# Testnet evidence protocol

How to reproduce every claim VERITENSOR makes, and where the raw record lives.

**Current status: VERITENSOR has NOT been deployed to a Bittensor subnet.**
No hotkey is registered, no weight has been submitted on chain, and no evidence
in this repository claims otherwise. What *has* been executed, and is recorded
under `evidence/`, is the complete subnet mechanism running across real
processes with real Bittensor wallets and the SDK's signed transport.

---

## 1. The three modes, and what evidence each one can support

Every evidence file records its mode in `manifest.json` and on every JSONL line.
They are mutually exclusive and never blended.

| Mode | Wallets | Transport | Chain | What it can prove |
| --- | --- | --- | --- | --- |
| `simulation` | none | in-process calls | none | the mechanism discriminates miners; scoring/emission maths |
| `local_neurons` | **real** (unfunded) | **btauth/1 signed HTTP** | none | the protocol, authentication, replay protection, dispatch, scoring and weight computation work across process boundaries |
| `bittensor_testnet` | real, registered, funded | btauth/1 | **yes** | on-chain registration, metagraph discovery, weight submission |

Evidence produced so far is `simulation` and `local_neurons`.
`bittensor_testnet` evidence requires the operator actions in
[`DEPLOYMENT_CHECKLIST.md`](DEPLOYMENT_CHECKLIST.md).

---

## 2. Evidence layout

```
evidence/
  <UTC timestamp>-<role>-<name>/
    manifest.json          mode, SDK probe, config, public wallet addresses
    miner/events.jsonl     start, solve, decline, timeout, stop
    validator/events.jsonl start, discovery, stop
    queries/queries.jsonl  every task dispatched (id, category, difficulty,
                           nonce, deadline, prompt hash + excerpt, targets)
    responses/…            every response, failure and mutation probe
    scores/scores.jsonl    every five-dimension breakdown and final score
    weights/weights.jsonl  every weight vector, with submitted / on_chain flags
    metrics/metrics.jsonl  periodic aggregates
    screenshots/           (manual, for a submission package)
    run.json               machine summary
    summary.md             human digest
  logs/                    stdout of each neuron process
```

Nothing is written unless the event happened. There is no "generate evidence"
command — the recorder is wired into the neuron code paths.

---

## 3. Reproducing the local-neuron run (about 3 minutes)

### Resource requirements

Each neuron is a separate Python process holding FastAPI plus the Bittensor
SDK — **~80–95 MB resident**. The reference 10-miner topology therefore needs
roughly **1 GB of free RAM**, and 13 neurons (10 miners + 3 validators) about
1.3 GB.

`scripts/start_miners.sh` checks available memory before launching and refuses
with a specific message rather than hanging on health checks:

```
[veritensor] resource check: need ~950 MB for 10 neurons, 537 MB available
[veritensor] NOT ENOUGH MEMORY: ~950 MB required, 537 MB available.
[veritensor] Options:
  • run a smaller topology:   VT_MINERS=5 ./scripts/start_miners.sh
  • stop the frontend dev server (it typically holds 600-900 MB)
```

On a constrained host, either stop the Next.js dev server first (it is by far
the largest consumer) or scale the topology down — nothing in the mechanism
assumes ten miners:

```bash
VT_MINERS=4 VT_VALIDATORS=2 ./scripts/start_miners.sh
VT_MINERS=4 VT_VALIDATORS=2 VT_ROUNDS=12 ./scripts/start_validators.sh
```


```bash
git clone <repo> && cd veritensor
pip install -r requirements-dev.txt        # includes the Bittensor SDK

# 1. create 10 miner + 3 validator UNFUNDED dev wallets under .wallets-dev/
./scripts/setup_testnet.sh

# 2. start 10 miner neurons (ports 9100–9109), each a separate process
./scripts/start_miners.sh

# 3. run 3 validator neurons for a bounded number of rounds
VT_ROUNDS=15 ./scripts/start_validators.sh

# 4. watch it work
tail -f evidence/logs/validator-00.log

# 5. stop
./scripts/stop_all.sh
```

### What a judge should check

```bash
# the transport was genuinely authenticated (not a mock)
curl -s localhost:9100/health | jq
#   → {"transport":"btauth/1","signed_transport":true,"hotkey_ss58":"5Cho..."}

# an unsigned request is refused
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  localhost:9100/veritensor/v1/verify -d '{}'
#   → 401

# every dispatched task, with its nonce and deadline
jq -r '.task_id + "  " + .category + "  d" + (.difficulty|tostring)' \
  evidence/*validator-00/queries/queries.jsonl | head

# every score, recomputable from its components
jq -c '{miner:.miner_uid, breakdown, final:.final_score}' \
  evidence/*validator-00/scores/scores.jsonl | head

# the weight vector, and the honest statement that it was not submitted
jq -c '{total, submitted, on_chain, reason}' \
  evidence/*validator-00/weights/weights.jsonl
```

### Observed result from the reference run

15 rounds × 10 miners, three independent validators, btauth/1 signed:

```
  Miner            Score      Weight
  --------------------------------------
  miner-09         0.705      0.171
  miner-00         0.689      0.157
  miner-01         0.665      0.136
  miner-08         0.651      0.125
  miner-02         0.636      0.114
  miner-04         0.609      0.095
  miner-03         0.605      0.092
  miner-05         0.539      0.055
  miner-06         0.538      0.054
  miner-07         0.211      0.000     ← gaming archetype, 14 boilerplate flags
  --------------------------------------
  TOTAL                       1.000
```

`miner-07` runs the gaming archetype: it earns **zero** emission. The weight
vector sums to exactly 1.0. Both facts come from
`evidence/<run>/weights/weights.jsonl`, not from this document.

---

## 4. Reproducing the in-process mechanism evidence

```bash
pytest tests/test_pipeline_integration.py -v    # 10 miners × 3 validators × 100 tasks
pytest tests/test_adversarial.py -q             # 29 attacks, writes docs/attack_report.json
python -m scripts.run_simulation --miners 50 --validators 5 --tasks 100
```

---

## 5. What a testnet run will add

Once the checklist is complete, the same commands produce chain-backed
evidence, distinguishable by `"mode": "bittensor_testnet"` and
`"on_chain": true`:

```bash
python -m scripts.preflight                    # must exit 0 first
VT_MODE=bittensor_testnet ./scripts/start_miners.sh
python -m subnet.neurons.validator --config configs/testnet.yaml --rounds 20
```

Additional records that only a real run can produce:

| Record | Where | Proves |
| --- | --- | --- |
| `validator.discovery` with `source: metagraph`, `block` | `validator/events.jsonl` | miners were found on chain, not from a config file |
| `weights.computed` with `submitted: true`, `extrinsic` | `weights/weights.jsonl` | the extrinsic hash of a real weight submission |
| `miner.serve_axon` | `miner/events.jsonl` | the axon endpoint was published on chain |

Cross-check any of them independently:

```bash
btcli wallet overview --wallet.name veritensor --subtensor.network test
btcli subnet metagraph --netuid <NETUID> --subtensor.network test
```

---

## 6. Anti-fabrication rules this repository follows

1. A record is written when the event occurs, never retrospectively.
2. `on_chain` is `true` only when a value came from a chain call.
3. The dashboard's mode banner is driven by the backend adapter, so it cannot
   claim a deployment the server is not performing.
4. `scripts/preflight.py` performs **reads only** and exits non-zero while any
   prerequisite is unmet.
5. `configs/testnet.yaml` ships inert (netuid 0) and fails validation until an
   operator supplies a real netuid — a test asserts this
   (`test_shipped_testnet_config_refuses_to_run_unconfigured`).
