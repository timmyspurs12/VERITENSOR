# Deployment checklist

Nothing below is ticked. Every unticked box is a real outstanding action, and
the ones marked **HUMAN** cannot be automated by this repository because they
involve key material, money, or a decision only the operator can make.

Verify progress at any time with the read-only preflight, which never signs or
submits anything:

```bash
python -m scripts.preflight --netuid <NETUID> --network test
```

---

## Environment

- [x] Python 3.11+ and Node 20+ available
- [x] Host sized for the topology — ~95 MB RAM per neuron (10 miners ≈ 1 GB);
      `start_miners.sh` verifies this before launching
- [x] `pip install -r requirements-dev.txt` (includes the Bittensor SDK)
- [x] Bittensor SDK present and a supported generation — verified 11.1.0
- [x] `bittensor.http_auth` (btauth/1) available for signed transport
- [x] Chain endpoint reachable for reads — verified against `test`
- [x] `.env` created from `.env.example`

## Wallet — **HUMAN**

- [ ] **Coldkey created** — `btcli wallet new_coldkey --wallet.name veritensor`
- [ ] **10 miner hotkeys created** — `btcli wallet new_hotkey --wallet.name veritensor --wallet.hotkey miner-00` … `miner-09`
- [ ] **3 validator hotkeys created** — `validator-00` … `validator-02`
- [ ] **Coldkey funded on testnet** — faucet or transfer; check with `btcli wallet balance --subtensor.network test`
- [ ] Wallet path recorded in `.env` (`BITTENSOR_WALLET_PATH`)

> Local **unfunded** dev wallets can be created automatically for the chainless
> mode with `./scripts/setup_testnet.sh`. They are written to `.wallets-dev/`,
> never to `~/.bittensor`, and are rejected by config validation in testnet
> mode.

## Network and subnet — **HUMAN**

- [ ] **Testnet selected** — `BITTENSOR_NETWORK=test`
- [ ] **Subnet chosen or created** — `btcli subnet list --subtensor.network test`, or `btcli subnet create` (burns TAO)
- [ ] **Netuid recorded** — `SUBNET_NETUID=<NETUID>` in `.env`
- [ ] Registration cost checked — preflight prints the current burn

## Registration — **HUMAN** (each registration burns TAO)

- [ ] **Miner hotkeys registered** — `btcli subnet register --netuid <NETUID> --wallet.name veritensor --wallet.hotkey miner-00 --subtensor.network test` (×10)
- [ ] **Validator hotkeys registered** (×3)
- [ ] Validator stake sufficient for a validator permit (subnet-dependent)
- [ ] `python -m scripts.preflight` exits 0

## Miner neurons

- [x] Miner neuron implemented and runnable — `python -m subnet.neurons.miner --config configs/miner.yaml`
- [x] Serves an authenticated axon (`/veritensor/v1/verify`) over btauth/1
- [x] Validates task schema, deadline and solve timeout
- [x] Returns answer, confidence, evidence and execution timing
- [x] Survives malformed requests and solver exceptions without dying
- [x] Records evidence per run
- [x] **10 miners run locally and serve real traffic** (chainless)
- [ ] **Axon endpoint published on chain** — `chain.serve_axon: true`, requires a registered hotkey
- [ ] **10 miners running against testnet**

## Validator neurons

- [x] Validator neuron implemented and runnable — `python -m subnet.neurons.validator --config configs/validator.yaml`
- [x] Generates tasks with hidden ground truth and an HMAC commitment
- [x] Dispatches signed, receiver-bound queries concurrently
- [x] Validates responses (schema, task binding, nonce, deadline, anti-gaming)
- [x] Scores across five dimensions and updates reputation
- [x] Issues adversarial mutation probes
- [x] Computes normalised weights summing to 1.0
- [x] Prints an inspectable score/weight table
- [x] **3 validators run locally against 10 miners** (chainless)
- [ ] **Miner discovery from the on-chain metagraph** — needs a real netuid
- [ ] **Weights submitted on chain** — `chain.submit_weights: true` + registered hotkey

## Mechanism

- [x] Scoring configurable, weights validated to sum to 1.0
- [x] All components normalised to `[0,1]`; NaN/inf impossible
- [x] Rolling reputation with EMA and a minimum-sample trust ramp
- [x] Outlier protection (latency winsorising, junk answers, per-task delta cap)
- [x] Emission normalisation: `Σ weights ∈ {0, 1}`, per-miner cap, zero-division safe
- [x] Anti-gaming suite: 29 adversarial tests, results in `docs/attack_report.json`

## Evidence

- [x] Evidence recorder writes timestamped JSONL per run
- [x] Mode (`simulation` / `local_neurons` / `bittensor_testnet`) on every record
- [x] Local-neuron run captured under `evidence/`
- [ ] **Testnet run captured** (`"on_chain": true` records)
- [ ] Screenshots collected for the submission package

## Frontend

- [x] Dashboard connected to the real backend
- [x] Three-state mode indicator driven by the backend adapter
- [x] Read-only chain status panel showing genuine unmet prerequisites
- [x] `RUN FULL DEMO` executes the real pipeline
- [ ] Frontend pointed at a testnet-backed validator

## Submission — **HUMAN**

- [ ] **Public GitHub repository published**
- [ ] **MVP deployed / reachable by judges**
- [ ] **Demo video recorded**
- [ ] **Pitch video recorded**
- [ ] HackQuest submission form completed

---

## Exact command sequence once the human steps are done

```bash
# 0. verify — must exit 0
python -m scripts.preflight --netuid <NETUID> --network test

# 1. publish miner axons on chain and start them
VT_MODE=bittensor_testnet \
VT_WALLET_NAME=veritensor \
VT_WALLET_PATH=~/.bittensor/wallets \
  ./scripts/start_miners.sh

# 2. start a validator that discovers miners on chain and submits weights
python -m subnet.neurons.validator --config configs/testnet.yaml \
  --netuid <NETUID> --network test --submit-weights --rounds 20

# 3. verify independently
btcli subnet metagraph --netuid <NETUID> --subtensor.network test
jq -c '{submitted, on_chain, extrinsic}' evidence/*validator*/weights/weights.jsonl
```

## Cost note

Registration burns TAO **per hotkey**. Thirteen hotkeys on the reference
topology at the burn rate printed by preflight is the minimum outlay, plus
transaction fees for `ServeAxon` and each `set_weights`. Start with fewer
miners if testnet funds are limited — nothing in the code assumes ten.
