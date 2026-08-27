# Final readiness report

**Date:** 2026-08-27
**Scope:** transformation of VERITENSOR from a local prototype into a
Bittensor-deployable subnet.
**Verdict:** the repository is **ready to become** a Bittensor subnet. It is
**not** one yet, and nothing in it claims otherwise.

---

## Verification performed for this report

| Check | Command | Result |
| --- | --- | --- |
| Python test suite | `pytest -q` | **211 passed** |
| Integration (10×3×100) | `pytest tests/test_pipeline_integration.py -v` | **18 passed** |
| Adversarial suite | `pytest tests/test_adversarial.py -q` | **29 passed** |
| Transport vs real SDK | `pytest tests/test_transport.py -q` | **13 passed** |
| Neuron + chain | `pytest tests/test_neurons.py -q` | **25 passed** |
| Frontend unit tests | `npx vitest run` | **10 passed** |
| TypeScript | `tsc --noEmit` | **clean** |
| Production build | `npm run build` | **16 routes built** |
| API acceptance | end-to-end script against the running stack | **18/18 passed** |
| Distributed run | 10 miner + 3 validator processes, btauth/1 | **15 rounds, Σw = 1.000** |
| Chain reads | `python -m scripts.preflight --netuid 1 --network test` | **live, block 7,873,228** |

---

## READY

### Subnet mechanism
- 13 task generators across 4 verifiable families; ground truth computed, never written.
- 18-item private held-out benchmark bank with rotation.
- Deterministic verifiers (7 kinds) including an AST-sandboxed predicate evaluator.
- Mutation engine producing provably answer-preserving variants.
- Five-dimension scoring from a single validated configuration object.
- Brier calibration, EMA reputation with a trust ramp, outlier protection.
- Emission model: `Σ weights ∈ {0,1}` exactly, per-miner cap, NaN/negative-proof.
- Adaptive difficulty with configurable bands and a non-adaptive control strategy.

### Runnable neurons
- `python -m subnet.neurons.miner --config configs/miner.yaml` — authenticated axon, real solver, evidence recording, graceful failure.
- `python -m subnet.neurons.validator --config configs/validator.yaml` — task generation, signed dispatch, grading, probes, reputation, weight computation, weight submission path.
- Layered configuration (defaults < YAML < env < CLI) with mode-aware validation that refuses unsafe testnet settings.
- 10-miner / 3-validator topology scripted and executed.

### Bittensor integration
- SDK **11.1.0** verified; capability probe reports precise errors on mismatch.
- btauth/1 signed transport with verified tamper, wrong-receiver and replay rejection.
- Chain reads verified live: block height, metagraph, registration burn cost.
- `set_weights`, `BurnedRegister`, `ServeAxon` wired to the real v11 APIs.
- Read-only `preflight` that exits non-zero while any prerequisite is unmet.

### Evidence and honesty controls
- Timestamped JSONL evidence per run; every record carries its mode and an `on_chain` flag.
- Three mutually exclusive modes surfaced in the API, the UI banner and the evidence manifests.
- `configs/testnet.yaml` ships inert and fails validation until configured (asserted by a test).
- `SUBNET_NETUID` defaults to `0`; the simulated subnet's display id is a separate setting.

### Application
- FastAPI backend: 21 endpoints, admin auth, rate limiting, security headers, structured logs.
- Next.js frontend: 16 routes, three-state mode banner, read-only chain status panel, one-click full demo.
- Docker compose with a `neurons` profile for standalone miner/validator containers.

### Documentation
`README` · `HACKATHON_SUBMISSION` · `IMPLEMENTATION_AUDIT` · `ARCHITECTURE` ·
`SCORING` · `MECHANISM` · `ANTI_GAMING` (with measured results) · `SECURITY` ·
`API` · `TESTNET` · `TESTNET_EVIDENCE` · `DEPLOYMENT_CHECKLIST` · `LIMITATIONS`.

---

## BLOCKED

Items that cannot be completed in this environment, with the precise reason.

| Item | Blocked by | Unblocks when |
| --- | --- | --- |
| **On-chain registration** | No funded coldkey. `BurnedRegister` burns TAO. | Operator funds a coldkey on testnet. |
| **On-chain weight submission** | `set_weights` requires a hotkey registered on the netuid; the chain rejects unregistered signers. | Registration completes. |
| **Metagraph miner discovery** | Requires a netuid where our miners have published axons via `ServeAxon`. | Registration + `chain.serve_axon: true`. |
| **Testnet evidence** (`on_chain: true`) | Produced only by a real run. | The two items above. |
| **Docker image build verification** | Docker is not available in the development sandbox. | Run `docker compose build` on any Docker host. |
| **Public deployment / MVP URL** | Requires hosting the operator controls. | Operator deploys. |
| **Demo and pitch videos** | Human recording. | Operator records. |

Nothing above was simulated, stubbed or approximated to appear complete.

---

## REQUIRES USER ACTION

Ordered. Each is a real-world action involving keys, money or judgement.

1. **Create wallets** — one coldkey, 10 miner hotkeys, 3 validator hotkeys.
   ```bash
   btcli wallet new_coldkey --wallet.name veritensor
   btcli wallet new_hotkey --wallet.name veritensor --wallet.hotkey miner-00   # ×10
   btcli wallet new_hotkey --wallet.name veritensor --wallet.hotkey validator-00  # ×3
   ```
2. **Fund the coldkey** on the test network (faucet or transfer).
   ```bash
   btcli wallet faucet --wallet.name veritensor --subtensor.network test
   btcli wallet balance --wallet.name veritensor --subtensor.network test
   ```
3. **Choose or create a subnet**, then record the netuid.
   ```bash
   btcli subnet list --subtensor.network test        # or: btcli subnet create
   ```
4. **Register each hotkey** (burns TAO per hotkey).
   ```bash
   btcli subnet register --netuid <NETUID> --wallet.name veritensor \
         --wallet.hotkey miner-00 --subtensor.network test
   ```
5. **Populate `.env`** — `SIMULATION_MODE=false`, `SUBNET_NETUID=<NETUID>`,
   `BITTENSOR_WALLET_NAME`, `BITTENSOR_HOTKEY_NAME`, and a real
   `VERITENSOR_COMMIT_SECRET` and `ADMIN_API_KEY`.
6. **Verify** — `python -m scripts.preflight` must exit 0.
7. **Approve on-chain transactions** — `ServeAxon` per miner and `set_weights`
   per validator cycle both cost fees.
8. **Publish the repository, deploy the MVP, record the videos.**

---

## Known defects found and fixed during this pass

Recorded because they are the substance of the work, and because an audit that
finds nothing is not an audit.

| Defect | Severity | Resolution |
| --- | --- | --- |
| Adapter written against removed v8/v9 APIs (`Synapse`, `Axon`, `Dendrite`, old `set_weights`) — would have failed on first real use | **critical** | Rewritten against verified v11 surface; capability probe added |
| Subnet could not run outside the FastAPI process | **critical** | `subnet/neurons/` — two standalone programs depending only on `subnet/` |
| Prompt reuse of 9.8% made memorisation viable | **high** | Generator parameter spaces widened; measured 0.75% |
| `wait_for_http` clobbered the caller's loop variable — infinite loop in `start_miners.sh` | high | All loop counters made `local` |
| FastAPI could not resolve a function-local `Request` annotation → every task rejected with 422 | high | Import moved to module scope |
| Alpha-denominated `Balance.tao` raised `UnitMismatchError`, breaking metagraph reads | high | `_as_float` reads `.amount` first, guards every accessor |
| Validators reported "wrong_receiver" because hotkeys were unknown | high | Unauthenticated `/health` discovery document + `resolve_hotkeys` |
| Identical solvers produced byte-identical evidence → honest miners flagged as colluding | medium | Per-operator phrasing; limitation documented |
| Wall-clock idleness marked healthy validators "stale" | medium | Activity-relative rule + two regression tests |
| Duplicate kwarg crashed the validator on shutdown | medium | Fixed; covered by the neuron run |
| A benchmark item leaked its answer via the roster ordering | medium | Item data corrected (not the test) |
| A stored benchmark answer disagreed with execution | medium | Answer corrected to the executed value |
| Simulation netuid 47 was used as the chain netuid, resolving to a stranger's testnet subnet | medium | Split into `SUBNET_NETUID` (default 0) and `SIMULATION_NETUID` |
| No outlier protection in scoring | medium | Latency winsorising, junk-answer guard, per-task delta clamp |

---

## Honest summary

The mechanism is real and measured. The neurons are real programs that talk
over the Bittensor SDK's own authenticated protocol with real keys, and the
chain client genuinely reads the live test network. The only thing standing
between this repository and a running testnet subnet is a funded wallet and the
registration transactions — and the code says so, out loud, in every place a
reader might otherwise assume more.
