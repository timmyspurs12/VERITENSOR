# Mechanism specification

This document is the normative description of the VERITENSOR incentive
mechanism. Every constant referenced here lives in
`subnet/scoring/config.py::MechanismConfig` and is served live at
`GET /api/mechanism/config`.

## 1. Objects

| Object | Owner | Visibility |
| --- | --- | --- |
| `TaskRequest` | validator → miner | public |
| `GroundTruth` | validator only | **never transmitted** |
| `MinerResponse` | miner → validator | public |
| `ScoreBreakdown` | validator | public after scoring |
| `MinerReputation` | validator | public |
| emission vector | validator | public, sums to 1 |

## 2. Scoring

```
final = (a·wa + e·we + r·wr + c·wc + l·wl) · (1 − Σpenalties)
```

with defaults `wa=0.45, we=0.20, wr=0.15, wc=0.10, wl=0.10` (validated to sum
to 1.0 at construction) and `Σpenalties` capped at 1.0. Every component is
clamped to `[0,1]`; `NaN`/`inf` map to `0.0` (`components.clamp`).

### 2.1 Accuracy

`verify(answer, ground_truth)` dispatches to a registered verifier:

| Verifier | Behaviour |
| --- | --- |
| `exact` | normalised string equality + configured aliases |
| `boolean` | yes/no polarity; hedged answers containing both polarities score 0 |
| `numeric` | `math.isclose` with per-task `atol`/`rtol`; last number in the text is extracted |
| `set_match` | F1 over an unordered set (partial credit) |
| `sequence` | positional match; partial credit halved so a near-miss ordering is not nearly as good as the right one |
| `multiple_choice` | option-label match |
| `python_predicate` | AST-validated sandboxed expression authored by the validator |

### 2.2 Evidence

```
evidence = 0.55·coverage + 0.25·structure + 0.20·specificity
```

* `coverage` — fraction of generator-declared concept keywords present. Miners
  never see these keywords.
* `structure` — supplied items / `max_useful_items` (5).
* `specificity` — `0.6·unique-token ratio + (0.4 if a digit appears else 0.15)`.
* Text under 24 characters, or matching the boilerplate blacklist, scores 0.05.
* No evidence at all scores 0.0 — correctness alone cannot earn this dimension.

### 2.3 Robustness

`robustness = EMA(probe outcomes, α = 0.3)` starting from a prior of 0.5.
A probe is a mutated task whose ground truth is provably identical to the
parent's; the outcome is `True` when the miner's answer is still correct.

Mutation kinds: identifier renaming, comment injection and whitespace changes
(code); paraphrase wrappers (math/pattern); constraint reordering (reasoning);
row shuffling (data). Output-prediction mutations are re-executed at generation
time and discarded if the return value changed — a mutation that alters the
answer is a generator bug, not a probe.

### 2.4 Calibration

```
brier       = mean((confidence − outcome)²) over the last 50 responses
calibration = 1 − min(brier, 0.25) / 0.25
```

Fewer than 5 samples → neutral prior 0.5.

| Behaviour | Brier | Calibration |
| --- | --- | --- |
| always 0.95, right 60% | 0.3625 | **0.000** |
| always 0.60, right 60% | 0.2400 | 0.040 |
| 0.95 when right / 0.10 when wrong | ≈0.005 | ≈0.98 |
| perfect and certain | 0.000 | 1.000 |

Discriminative honesty, not modesty, is what pays.

### 2.5 Latency

```
latency = 1.0                                   if t ≤ 1200 ms
        = max(0.05, 1 − (t − 1200)/(15000−1200)) if 1200 < t < 15000 ms
        = 0.05                                   otherwise
```

A **budget**, deliberately not a relative ranking: rewarding "fastest" invites
answering instantly and wrongly, which the accuracy weight then has to undo.

## 3. Reputation

```
EMA_t      = (1 − α)·EMA_{t−1} + α·score_t          α = 0.15
trust      = min(1, task_count / 20)
reputation = trust·EMA + (1 − trust)·prior_component
```

Consequences:
* one task moves reputation by at most `α·|score − EMA|`;
* a fresh miner with one perfect task lands below 0.5;
* long-run reputation converges to the miner's true expected score.

Per-category statistics, latency samples, probe outcomes, flag counts and a
bounded history (500 snapshots) are tracked alongside.

## 4. Emissions

```
for each miner:
    reject if task_count < min_tasks (10)          → weight 0
    reject if reputation < floor_score (0.25)      → weight 0
    surplus = reputation − floor_score
    raw     = surplus ^ temperature (2.5)
normalise raw to sum 1
enforce cap = max(max_share (0.25), 2/n) by clipping and redistributing
renormalise; assign residual float drift to the top miner
```

Why each guard exists:

* **`min_tasks`** — small-sample luck cannot buy a top allocation.
* **`floor_score`** — miners performing near chance earn nothing; the subnet
  does not subsidise noise.
* **`temperature > 1`** — the reward gradient is superlinear in quality, so
  improving is worth more than coasting.
* **`max_share`** — no single miner captures the subnet. Relaxed to `2/n` in
  small networks: with a hard 25% cap and 3 miners the cap would bind on
  everyone and flatten the distribution, destroying the very signal the
  mechanism exists to produce.
* **residual assignment** — guarantees the vector sums to exactly 1 after
  rounding.

## 5. Adaptive difficulty

| Score | Band | Difficulty range |
| --- | --- | --- |
| `< 0.60` | easy | 1–3 |
| `0.60–0.80` | normal | 4–6 |
| `0.80–0.90` | hard | 7–8 |
| `≥ 0.90` | adversarial | 9–10 |

The goal is to keep tasks in the informative band. Too easy and every miner
saturates, so the score carries no information; too hard and the signal is
noise. The `fixed_baseline` validator opts out and always issues difficulty 5,
giving a control against which the adaptive regime can be compared.

## 6. Consensus

```
agreement               = weight of the largest identical-answer cluster / total
                          (weights = 0.1 + reputation)
correct_share           = verified-correct responses / graded responses
verification_confidence = 0.5·agreement + 0.5·correct_share
```

Reported for observability and used as the grading signal only for
`VerificationType.CONSENSUS` tasks. For `EXACT`, `PROGRAMMATIC` and
`ADVERSARIAL` tasks the deterministic verifier is authoritative — a colluding
majority must not be able to define truth.

## 7. Invariants (all covered by tests)

1. `Σ weights ∈ {0, 1}` exactly.
2. `0 ≤ every component, score, weight ≤ 1`.
3. `NaN`/`inf` reputation cannot propagate into emissions.
4. No miner exceeds `max_share` when the population makes the cap feasible.
5. A response bound to task A cannot be scored against task B.
6. Ground truth is absent from every non-admin API projection.
7. Better verified miners receive strictly more emission than worse ones.
