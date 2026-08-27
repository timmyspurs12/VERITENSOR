# Scoring specification

Normative description of every formula in the VERITENSOR mechanism. All
constants live in [`subnet/scoring/config.py`](../subnet/scoring/config.py) and
are served live at `GET /api/mechanism/config`, so this document and the running
system cannot drift apart.

---

## 1. Configuration object

```python
MechanismConfig(
    weights=ScoreWeights(accuracy=.45, evidence=.20, robustness=.15,
                         calibration=.10, latency=.10),
    latency=LatencyPolicy(target_ms=1200, timeout_ms=15_000, floor=.05),
    calibration=CalibrationPolicy(window=50, worst_brier=.25, min_samples=5, prior=.5),
    evidence=EvidencePolicy(keyword_weight=.55, structure_weight=.25,
                            specificity_weight=.20, min_chars=24,
                            max_useful_items=5, empty_score=0.0),
    robustness=RobustnessPolicy(probe_rate=.35, prior=.5, alpha=.3),
    reputation=ReputationPolicy(ema_alpha=.15, min_tasks_for_full_trust=20,
                                prior_score=.35, history_limit=500),
    outliers=OutlierPolicy(latency_clamp_ms=120_000, max_answer_chars=16_000,
                           min_meaningful_chars=1, max_single_task_delta=.5),
    penalties=PenaltyPolicy(duplicate_response=.45, boilerplate_evidence=.20,
                            schema_violation=.50, replay_attempt=1.0,
                            deadline_miss=.30, cap=1.0),
    emission=EmissionPolicy(temperature=2.5, floor_score=.25, max_share=.25,
                            min_tasks=10),
    difficulty=DifficultyPolicy(easy_below=.60, normal_below=.80, hard_below=.90),
)
```

`ScoreWeights.validate()` raises unless the five weights sum to `1.0`. Override
them per deployment with `VERITENSOR_SCORE_WEIGHTS` (JSON) or the `scoring:`
block of a validator config; nothing in the codebase hardcodes a weight twice.

---

## 2. Final score

```
final = ( accuracy    · w_a
        + evidence    · w_e
        + robustness  · w_r
        + calibration · w_c
        + latency     · w_l ) · (1 − min(Σ penalties, cap))
```

Every component is passed through `clamp()`, which maps `NaN`, `±inf` and
non-numeric input to `0.0` and bounds the rest to `[0, 1]`. The product of
bounded values and a factor in `[0, 1]` is therefore always in `[0, 1]`:
**a negative or `NaN` score cannot be constructed.**

---

## 3. Components

### 3.1 Accuracy — 45%

```
accuracy = verify(answer, ground_truth)      ∈ {0, 1} or [0,1] with partial credit
```

Dispatches to a registered verifier. Junk answers (whitespace, punctuation-only,
over `max_answer_chars`) short-circuit to `0.0` before a verifier runs.

| Verifier | Semantics |
| --- | --- |
| `exact` | normalised equality + configured aliases |
| `boolean` | polarity match; answers containing both polarities score 0 |
| `numeric` | `math.isclose` with per-task `atol`/`rtol`; last number extracted |
| `set_match` | F1 over an unordered set (partial credit) |
| `sequence` | positional match; partial credit halved |
| `multiple_choice` | option-label match |
| `python_predicate` | AST-validated sandboxed expression (validator-authored) |

### 3.2 Evidence quality — 20%

```
evidence = 0.55·coverage + 0.25·structure + 0.20·specificity

coverage    = |declared keywords present| / |declared keywords|     (0.5 if none declared)
structure   = min(items, 5) / 5
specificity = clamp(0.6 · unique_token_ratio + (0.4 if any digit else 0.15))
```

Deliberately **not** model-judged: an LLM judge would be non-deterministic and
itself gameable. Concept keywords are declared by the generator and never shown
to miners. Empty evidence scores `0.0`; recognised boilerplate or junk scores
`0.05`.

### 3.3 Robustness — 15%

```
robustness_0 = 0.5                                   (prior; untested ≠ free marks)
robustness_t = (1 − α)·robustness_{t−1} + α·outcome  α = 0.3
```

`outcome ∈ {0,1}` is whether a semantics-preserving mutation of a
previously-correct task was still answered correctly.

### 3.4 Confidence calibration — 10%

```
brier       = (1/N) Σ (confidence_i − outcome_i)²    over the last 50 responses
calibration = 1 − min(brier, 0.25) / 0.25
```

Fewer than 5 samples → prior `0.5`.

| Behaviour | Brier | Calibration |
| --- | --- | --- |
| always 0.95, right 60% | 0.3625 | **0.000** |
| always 0.60, right 60% | 0.2400 | 0.040 |
| 0.95 when right, 0.10 when wrong | ≈0.005 | ≈0.98 |
| perfectly certain and correct | 0.000 | 1.000 |

Modesty is not rewarded; **discrimination** is.

### 3.5 Latency — 10%

```
t = min(reported_ms, 120_000)                        (winsorised)

latency = 1.0                                        t ≤ 1200
        = max(0.05, 1 − (t − 1200)/13_800)           1200 < t < 15_000
        = 0.05                                       t ≥ 15_000
```

A **budget**, not a ranking. Rewarding relative speed would invite answering
instantly and wrongly, which the accuracy term would then have to undo.

---

## 4. Penalties

| Flag | Deduction | Trigger |
| --- | --- | --- |
| `replay_attempt` | 1.00 | task/nonce mismatch, or a second submission |
| `schema_violation` | 0.50 | malformed protocol payload |
| `duplicate_response` | 0.45 | repeated answer fingerprint (threshold varies by answer space) |
| `deadline_miss` | 0.30 | response after the deadline |
| `boilerplate_evidence` | 0.20 | reused or blacklisted evidence body |
| `evidence_collusion` | 0.00 | identical evidence across ≥3 miners (flag only) |

Deductions are summed, capped at `1.0`, and applied multiplicatively.

---

## 5. Reputation

```
EMA_t      = (1 − α)·EMA_{t−1} + α·clamp_outlier(score_t)     α = 0.15
trust      = min(1, task_count / 20)
reputation = trust·EMA + (1 − trust)·shrunk_prior
```

where `clamp_outlier` bounds a single task score to ±0.5 of the current EMA.

Consequences, all covered by tests:

* one task moves reputation by at most `α · |score − EMA|`;
* a fresh miner with one perfect task lands **below 0.5**;
* long-run reputation converges on the miner's true expected score.

---

## 6. Emissions

```
eligible  = task_count ≥ 10  ∧  reputation ≥ 0.25
surplus   = reputation − 0.25
raw       = surplus ^ 2.5
weight    = raw / Σ raw
cap       = max(0.25, 2/n)             # relaxed for small networks
weight    = redistribute(clip(weight, cap))
weight    = weight / Σ weight          # final renormalisation
residual  → assigned to the top miner so the vector sums to exactly 1
```

Guarantees enforced in `subnet/scoring/emissions.py` and asserted in
`tests/test_emissions.py`:

1. `Σ weights ∈ {0.0, 1.0}` exactly.
2. No weight is negative, `NaN` or infinite.
3. No miner exceeds `max_share` when the population makes the cap feasible.
4. A miner under `min_tasks` or below `floor_score` receives exactly `0`.
5. Better verified miners receive strictly more than worse ones.

Why each guard exists:

* **`min_tasks`** — small-sample luck cannot buy an allocation.
* **`floor_score`** — the subnet does not subsidise near-chance performance.
* **`temperature > 1`** — the reward gradient is superlinear in quality.
* **`max_share`** — no single miner captures the subnet.
* **`2/n` relaxation** — with 3 miners a hard 25% cap binds on everyone and
  flattens the distribution, destroying the signal the mechanism exists to
  produce.

### 6.1 Chain submission

```python
uid_map = weights_to_uid_map(weights)         # {uid: float}, zeros dropped
bittensor.set_weights(netuid, uid_map, wallet=..., hotkey=...,
                      mechid=0, version_key=0, network="test")
```

SDK v11 performs clipping, normalisation and u16 quantisation itself.
`weights_to_bittensor()` (explicit u16 pair) is retained for older SDK
generations and for showing operators the quantised vector.

---

## 7. Adaptive difficulty

| Score | Band | Difficulty |
| --- | --- | --- |
| `< 0.60` | easy | 1–3 |
| `0.60–0.80` | normal | 4–6 |
| `0.80–0.90` | hard | 7–8 |
| `≥ 0.90` | adversarial | 9–10 |

Thresholds are configuration. The `fixed_baseline` validator strategy opts out
entirely (always difficulty 5), providing a control group.

---

## 8. Consensus (observability only)

```
agreement               = weight of largest identical-answer cluster / total
                          (cluster weight = 0.1 + reputation)
correct_share           = verified-correct / graded
verification_confidence = 0.5·agreement + 0.5·correct_share
```

Used as a grading signal **only** for `VerificationType.CONSENSUS`. For
`EXACT`, `PROGRAMMATIC` and `ADVERSARIAL` the deterministic verifier is
authoritative — otherwise a colluding majority could define truth, which
`tests/test_adversarial.py::test_a_wrong_majority_cannot_define_truth` verifies
it cannot.
