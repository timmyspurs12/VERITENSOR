# VERITENSOR — Hackathon submission

## Project name

**VERITENSOR**

## Tagline

**The decentralized verification layer for machine intelligence.**

---

## Problem

Machine-generated answers are abundant and nearly free. Knowing which ones are
*correct* is neither.

* **Verification does not scale.** Establishing that an answer is right still
  needs a human or a deterministic checker. Generation volume has grown orders
  of magnitude faster than verification capacity.
* **Static benchmarks decay into answer keys.** The moment a benchmark is
  public it measures memorisation. It stops being informative exactly when it
  becomes popular.
* **Confidence is unpriced.** A model right 60% of the time while claiming 95%
  certainty is more dangerous than one that admits doubt. Nothing in the
  current stack charges for miscalibration.
* **Robustness is untested.** An answer that flips when you rename a variable
  was pattern matching, not knowledge.

## Solution

VERITENSOR makes verification itself the commodity the subnet produces.

A validator generates a task whose answer it already knows but has never
published, and commits to that answer with an HMAC before dispatch. Miners
answer over authenticated transport. The validator grades five dimensions,
probes robustness with a semantics-preserving mutation of the same problem, and
converts the result into a normalised emission weight.

```
TASK → MINERS → ANSWERS → VALIDATORS → VERIFICATION → REPUTATION → EMISSIONS → BETTER MINERS
```

The core principle: **do not reward miners for producing AI output; reward
output that survives independent verification.**

## Why Bittensor

Bittensor pays for work that is scarce, objectively measurable and hard to
fake. Verification fits precisely.

* **Measurable.** Correctness against hidden, programmatically computed ground
  truth is not a matter of taste — two honest validators grading the same
  answer produce the same number.
* **Hard to fake.** Ground truth is never published, tasks are regenerated from
  seeds, and mutation probes punish memorisation. No shortcut is cheaper than
  being right.
* **Naturally decentralised.** Independent validators with different strategies
  are strictly better than one grader: they make overfitting to a single
  evaluator unprofitable.
* **Useful off-subnet.** "This system is right X% of the time on verifiable
  tasks and knows when it isn't" is exactly what anyone shipping models to
  production needs to buy.

---

## Subnet architecture

```
┌── validator neuron ────────────────────────────────────────────┐
│  task engine (hidden ground truth + HMAC commitment)           │
│  strategy → sample miners                                      │
│  btauth/1 signed dispatch ──────────────────────┐              │
│  anti-gaming guard · scoring engine · reputation │              │
│  emission model → bittensor.set_weights          │              │
└──────────────────────────────────────────────────┼─────────────┘
                                                   ▼
┌── miner neuron ────────────────────────────────────────────────┐
│  authenticated axon: POST /veritensor/v1/verify                │
│  verify signature · receiver binding · skew · nonce replay     │
│  solver: heuristic | archetype-degraded | model backend        │
│  → answer + confidence + evidence + timing                     │
└────────────────────────────────────────────────────────────────┘
```

The subnet core (`subnet/`) has no dependency on the web backend, the database
or the frontend. The two neurons are ordinary long-lived programs:

```bash
python -m subnet.neurons.miner     --config configs/miner.yaml
python -m subnet.neurons.validator --config configs/validator.yaml
```

**SDK note.** Bittensor 11 removed `Synapse`, `Axon` and `Dendrite` and
replaced them with `bittensor.http_auth` — a normative signed-HTTP protocol
(`btauth/1`). VERITENSOR implements its transport on that protocol, verified
against the installed SDK, rather than against older documentation. The
capability probe in `subnet/chain/sdk.py` reports a precise error if a
different generation is installed.

## Miner responsibilities

1. Load a configured wallet/hotkey (never hardcoded; never generated on testnet).
2. Serve an authenticated axon and reject unsigned, replayed, stale or
   misaddressed requests before doing any work.
3. Validate the task: schema, deadline, category.
4. **Actually solve it.** The reference `HeuristicSolver` scores ~99% on the
   generated pool by executing code, doing modular arithmetic, running
   constraint search, and computing statistics — no privileged information.
5. Return answer, calibrated confidence, evidence and execution timing.
6. Survive malformed input and solver failures without dying.
7. Expect an adversarial mutation of anything it answered correctly.

## Validator responsibilities

1. Generate a task; compute ground truth; publish an HMAC commitment.
2. Discover miners — static list locally, on-chain metagraph on testnet.
3. Dispatch signed, receiver-bound queries concurrently.
4. Validate every response (task binding, nonce, deadline, rate, duplicates).
5. Score accuracy, evidence, robustness, calibration, latency.
6. Issue mutation probes after correct answers.
7. Smooth scores into reputation with a minimum-sample trust ramp.
8. Compute a normalised weight vector and submit it with
   `bittensor.set_weights`.

## Task generation

13 generators across four verifiable families. Ground truth is **computed**,
never hand-written.

| Family | Generators | How truth is established |
| --- | --- | --- |
| Code security | `code.vulnerability`, `code.bug_detection`, `code.output_prediction` | known by construction; output prediction executes the reference implementation |
| Mathematics | `math.algebra`, `math.probability`, `math.numerical`, `math.modular` | solved analytically from the random parameters |
| Logical reasoning | `reasoning.ordering`, `reasoning.constraints`, `reasoning.pattern` | brute-force verified to have exactly one solution before publication |
| Data analysis | `data.anomaly`, `data.statistic`, `data.relationship` | outliers injected by construction; statistics from the stdlib |

Plus a private held-out benchmark bank (18 items) served only through benchmark
rotation.

## Evaluation

Deterministic verifiers only — never an LLM judge, because grading must be
reproducible: `exact`, `boolean`, `numeric`, `set_match`, `sequence`,
`multiple_choice`, and an AST-sandboxed `python_predicate`.

## Scoring

```
final = (accuracy·0.45 + evidence·0.20 + robustness·0.15
         + calibration·0.10 + latency·0.10) · (1 − penalties)
```

Full derivations in [`SCORING.md`](SCORING.md). Calibration uses a Brier score
over a 50-response window; latency is a *budget*, not a race.

## Reputation

`EMA(α=0.15)` with a trust ramp `min(1, tasks/20)` toward a low prior, plus
outlier clamping. A fresh miner with one perfect task lands below 0.5.

## Emission

`eligibility → floor subtraction → temperature 2.5 → normalise → per-miner cap
→ renormalise`. Guaranteed: `Σ weights ∈ {0, 1}`, no negatives, no NaN, no
miner over the cap, nothing for miners under 10 scored tasks.

## Anti-gaming

29 adversarial tests play each attack against the real pipeline; measurements
are written to `docs/attack_report.json` and tabulated in
[`ANTI_GAMING.md`](ANTI_GAMING.md). Highlights, all measured:

| Attack | Result |
| --- | --- |
| Memorise prompts | 0.75% prompt reuse over 400 draws |
| Constant-answer farming | 0.0% emission, 52 duplicate + 59 boilerplate flags |
| Confidence inflation (0.95 @ 60% accuracy) | calibration **0.000** |
| Replay across tasks / duplicate submission | rejected before scoring |
| 100 sybils with one perfect task each | **0.0%** of emissions |
| Hostile majority (6 of 10 miners) | honest miners take **89.2%** |

The suite also *found real weaknesses* and they were fixed rather than
excused: prompt reuse was 9.8% before the generator parameter spaces were
widened.

## Testnet deployment

**Status: not deployed.** No hotkey is registered and no weight has been
submitted on chain. This is stated everywhere it could otherwise be assumed —
in the UI banner, in `preflight`, and on every evidence record.

What *is* verified against the real SDK and the real chain:

| Capability | Status |
| --- | --- |
| SDK 11.1.0 detected, supported generation | ✅ verified |
| Wallet creation, sr25519 signing | ✅ verified |
| btauth/1 sign → verify, tamper and replay rejection | ✅ verified |
| Chain read: `subtensor("test").block` | ✅ verified (live) |
| Chain read: `subnets.metagraph(netuid=…)` | ✅ verified (live) |
| Registration (`BurnedRegister`) | ⛔ needs funded coldkey — **human** |
| Weight submission (`set_weights`) | ⛔ needs registered hotkey — **human** |

Everything blocking deployment is enumerated in
[`DEPLOYMENT_CHECKLIST.md`](DEPLOYMENT_CHECKLIST.md).

## Results

**In-process mechanism** — 10 miners × 3 validators × 100 tasks, executed by
`tests/test_pipeline_integration.py`, assertions made against live values:

* archetypes separate by > 0.25 reputation spread;
* the hallucinating miner (54% accurate, ~0.99 confidence) is beaten by a
  calibrated peer;
* the gaming archetype earns ≤ 2% emission;
* `Σ emission weights = 1.0` exactly.

**Distributed neurons** — 10 miner processes + 3 validator processes, real
wallets, btauth/1 signed HTTP, 15 rounds:

```
  Miner            Score      Weight
  miner-09         0.705      0.171
  miner-00         0.689      0.157
  ...
  miner-07         0.211      0.000     ← gaming archetype
  TOTAL                       1.000
```

Raw records: `evidence/<run>/{queries,responses,scores,weights}/*.jsonl`.

**Scale** — 50 miners × 5 validators × 100 tasks completes in ~0.8 s
in-process.

**Tests** — 211 Python tests + 10 frontend tests, all passing.

## Limitations

Stated plainly; a verification project that overstates itself is a
contradiction. Full list in [`LIMITATIONS.md`](LIMITATIONS.md).

* No testnet deployment has occurred.
* Miner "archetypes" degrade a genuinely computed answer; they are a model of
  operator quality, not evidence about any AI system.
* Evidence scoring is lexical and gameable by subtle padding; entailment
  checking is the intended replacement and is not implemented.
* Collusion detection catches byte-identical evidence only.
* Rate limiting is in-process; horizontal scaling needs a shared limiter.
* The ground-truth commitment is not yet published on chain.

## Roadmap

| Horizon | Item |
| --- | --- |
| Now | Local subnet + distributed neurons with signed transport, 211 tests |
| Next | Register 10 miner + 3 validator hotkeys on testnet; publish weights |
| Then | On-chain commit–reveal so grading is externally auditable |
| Then | Real model miners competing against the heuristic baseline |
| Later | Entailment-based evidence scoring |
| Later | Verification marketplace — external clients pay for scored verdicts |

---

*Independent hackathon project. Not affiliated with, sponsored by, or endorsed
by the Opentensor Foundation.*
