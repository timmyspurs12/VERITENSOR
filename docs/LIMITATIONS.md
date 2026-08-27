# Limitations

Written plainly. A verification project that overstates its own status would be
self-refuting.

## Deployment
* **No live testnet deployment has been performed from this repository.** No
  hotkey is registered and no weight has been submitted on chain. Chain
  *reads* (block height, metagraph, registration burn) are verified against the
  live test network; chain *writes* require a funded coldkey.
* SDK calls target **bittensor 11.1.0**, verified by probing the installed
  package. Earlier generations (v8/v9) exposed `Synapse`/`Axon`/`Dendrite`,
  which v11 removed; VERITENSOR does not emulate them and the capability probe
  reports a precise error if such an SDK is installed.
* Docker images are **config-reviewed, not build-verified** — Docker is not
  available in the development sandbox.

## Miners
* **In-process simulation** hands a miner its result through a harness oracle
  (`subnet/miner/oracle.py`) and the profile decides whether to emit it. That
  affordance is unreachable from the validator, the API or a neuron process.
* **Neuron processes cannot use the oracle** — they receive only the public
  task — so they run `HeuristicSolver`, a genuine solver (~99% on the generated
  pool: it executes code, does modular arithmetic, runs constraint search and
  computes statistics). `ProfiledSolver` then degrades that real answer to
  model a weaker or dishonest operator.
* The heuristic solver is a *baseline*, not a claim about AI capability. It is
  strong precisely because these tasks are deterministically verifiable.
* `ModelMiner` + `OpenAICompatibleBackend` is wired and works, but no
  large-scale grading of real models was run inside the hackathon window.

## Task coverage
* Only **deterministically verifiable** problems are included. Open-ended
  generation quality, style and long-form reasoning cannot be scored by this
  mechanism, and the project does not claim otherwise.
* Generator templates are finite. Parameters vary on every draw, but a
  determined observer will eventually enumerate the template families.
* Reasoning generators brute-force solution uniqueness, which bounds their size
  (≤ 6 entities) for tractability.

## Scoring
* Evidence scoring is **lexical**, not semantic. Keyword coverage plus structure
  and specificity can be gamed by padding with expected technical terms.
  Entailment-based verification is the intended replacement.
* Calibration uses a rolling window of 50 responses; a miner that changes
  behaviour is scored on a lagging estimate.
* Latency is self-reported by the miner. The validator also measures
  round-trip time (recorded in the evidence as `round_trip_ms`) but scores the
  reported value, winsorised at 120 s. Scoring measured RTT instead would
  penalise network distance rather than compute quality; the trade-off is that
  a miner can under-report. A future version should score
  `min(reported, measured)`.

## Anti-gaming
* Duplicate detection is a heuristic tuned for a low false-positive rate, so it
  under-detects.
* Collusion detection catches byte-identical evidence only; a paraphrasing
  cartel is not detected. It also cannot distinguish a cartel from independent
  operators running the same open-source solver — the reference solver
  therefore varies its phrasing per operator, which is realistic but means the
  detector is weaker than its flag count suggests.
* The ground-truth commitment is verifiable only against the validator's own
  record until it is published on chain.

## Engineering
* Rate limiting is in-process; horizontal scaling requires a shared limiter.
* The in-memory `SubnetNetwork` is the source of truth during a session.
  PostgreSQL/SQLite persistence is a durable mirror, not an event-sourced log:
  restarting reseeds the network rather than replaying history.
* Simulation throughput (thousands of tasks per minute) reflects an in-process
  loop, not chain-paced epochs. The dashboard labels it `simulated`.
* The event bus is bounded (5 000 events) and in-memory; there is no message
  broker.

## Testing
* 211 Python tests and 10 frontend tests cover the mechanism, transport,
  neurons, API contract, adversarial behaviour and security invariants. There
  is no browser end-to-end suite; frontend correctness is covered by strict
  TypeScript, a production build check and the API contract tests behind it.
* Chain tests are skipped automatically when the network is unreachable
  (`VERITENSOR_SKIP_NETWORK_TESTS=1` forces this), so a green suite offline
  does **not** imply chain connectivity was exercised.
