# Anti-gaming: design, measured results, and limitations

The threat model is a rational miner maximising emission weight per unit of
compute. The mechanism's job is to make "actually be right" the cheapest
available strategy.

Every claim in this document is produced by
[`tests/test_adversarial.py`](../tests/test_adversarial.py), which plays each
attack against the real pipeline and writes its measurements to
`docs/attack_report.json`. Re-run it with:

```bash
pytest tests/test_adversarial.py -q
```

---

## 1. Measured results

Latest run of the adversarial suite (29 tests, all passing):

| Attack | Defence | Outcome | Measurement |
| --- | --- | --- | --- |
| A1 memorisation | dynamic generation from random seeds | **defeated** | `prompt_reuse_rate=0.0075`, `samples=400` |
| A10 evidence keyword stuffing | coverage capped; specificity + structure terms | **mitigated** | `honest=0.419`, `stuffed=0.0` |
| A11 hostile-majority network | full mechanism | **defeated** | `honest_miners=4`, `honest_share=0.8916`, `hostile_miners=6`, `hostile_share=0.1084` |
| A2 replay (cross-task) | nonce + task binding | **defeated** | `reason=nonce_mismatch` |
| A2 replay (duplicate submit) | per-(task,miner) submission ledger | **defeated** | `reason=duplicate_submission` |
| A3 constant-answer farming | accuracy weight + duplicate detection + boilerplate evidence | **defeated** | `cheat_emission=0.0`, `cheat_reputation=0.0796`, `flags={'boilerplate_evidence': 59, 'duplicate_response': 52}`, `honest_reputation=0.653` |
| A4 confidence inflation @0.9 | Brier-based calibration over a rolling window | **defeated** | `accuracy=0.6`, `calibration=0.0` |
| A4 confidence inflation @0.95 | Brier-based calibration over a rolling window | **defeated** | `accuracy=0.6`, `calibration=0.0` |
| A4 confidence inflation @0.99 | Brier-based calibration over a rolling window | **defeated** | `accuracy=0.6`, `calibration=0.0` |
| A5 shallow pattern matching | adversarial mutation probes | **defeated** | `brittle_hold_rate=0.0`, `brittle_reputation=0.6465`, `stable_hold_rate=1.0`, `stable_reputation=0.7942` |
| A6 benchmark scraping | hidden ground truth + private bank | **defeated** | `checked=33`, `leaks=0` |
| A6b task-type detection | benchmark rotation | **mitigated** | `distribution={'adversarial': 13, 'generated': 80, 'hidden_benchmark': 19, 'mutation': 8}` |
| A7 collusion (identical evidence) | cross-miner evidence fingerprints | **detected** | `flag_count=3` |
| A7b colluding majority | verifier is authoritative, not consensus | **defeated** | `agreement=0.833333`, `cartel_score=0.225`, `correct_share=0.166667`, `honest_score=0.675` |
| A8 sybil / small sample | minimum sample + trust ramp | **defeated** | `honest_share=1.0`, `sybil_share=0.0` |
| A9 API abuse | per-miner token bucket + per-IP middleware | **defeated** | `allowed_of_200=10` |

`defeated` = the attack earns strictly less than honest behaviour.
`detected` = the attack is flagged for operators but not automatically priced.
`mitigated` = the attack is bounded but a sophisticated variant remains viable.

---

## 2. Mechanisms and what each one actually stops

### 2.1 Dynamic task generation
13 generators build tasks from random parameters; ground truth is computed at
generation time. Measured prompt reuse is **0.75%** over 400 draws.

> **This was weaker before the audit.** The first measurement was 9.8%, caused
> by small parameter spaces in `code.vulnerability` (4 builders × 2 verdicts)
> and `code.bug_detection` (3 function names × 2 shapes). The generators were
> widened — more tables, columns, function names, accumulators, sink styles and
> numeric ranges — rather than relaxing the test. The finding and the fix are
> both in `docs/IMPLEMENTATION_AUDIT.md`.

### 2.2 Hidden ground truth
`GroundTruth` never crosses the validator boundary. `TaskRequest` has no field
for it, `TaskRecord.public_dict()` omits it, and the repository's
`PUBLIC_TASK_COLUMNS` cannot select it. The only path is an authenticated admin
route that additionally refuses tasks which are still open.

### 2.3 CSPRNG identifiers and nonces
`secrets.token_hex` for every task id and nonce. 500 consecutive draws produced
500 distinct ids.

### 2.4 Commitment
Before dispatch the validator records
`HMAC(secret, task_id | nonce | answer)`. It cannot retrofit an answer after
seeing responses. **Limitation:** the commitment is currently verifiable only
against the validator's own record; publishing it on chain is the roadmap item
that closes this.

### 2.5 Replay protection
A response must carry the matching `task_id` **and** echo the server-issued
nonce, and `(task_id, miner_uid)` may be submitted once. On the wire this is
enforced twice: once by the guard, and once by the transport, because
`bittensor.http_auth` binds every request to a nonce, a receiver hotkey and a
body hash. Reusing a captured request against a different miner raises
`wrong_receiver`; replaying it against the same miner raises `ReplayedRequest`.

### 2.6 Task mutation and adversarial evaluation
After a correct answer a validator may issue a semantics-preserving mutation:
renamed identifiers, injected comments, shuffled constraints or rows,
paraphrased wording. The answer is provably unchanged (output-prediction
mutations are re-executed and discarded if the value moves). A miner that flips
loses 15% of its score directly and drags its robustness EMA down for every
later task.

### 2.7 Duplicate and boilerplate detection
Answer fingerprints per miner; evidence-body fingerprints; a blacklist of
recognised filler phrases. Enum answers (yes/no, A–D) legitimately repeat, so
the duplicate threshold is 18 for enum-typed schemas and 3 for open-ended ones
— a deliberate trade of recall for a near-zero false-positive rate on honest
miners.

### 2.8 Confidence calibration
Brier score over the last 50 responses, normalised to `[0,1]`. A miner at 0.95
confidence and 60% accuracy scores **0.000**; the same accuracy with honest,
discriminative confidence scores **> 0.8**.

### 2.9 Benchmark rotation
Each draw is generated, drawn from the private held-out bank, or an adversarial
mutation. A miner cannot tell which, so it cannot special-case the graded set.

### 2.10 Rate limiting
Per-miner token bucket in the guard, per-IP fixed window in the API middleware
(stricter for simulation routes), and server-side bounds on simulation size.
**Limitation:** both are in-process; a multi-replica deployment needs a shared
limiter (Redis `SET NX EX`) or a gateway.

### 2.11 Outlier protection
Added during the readiness pass:

* reported latency is winsorised at 120 s before scoring, so clock skew or a
  fabricated duration cannot dominate the latency component;
* answers/evidence that are whitespace, punctuation runs, or oversized are
  treated as junk and score zero without reaching a verifier — this is what
  reduces gross keyword stuffing to `0.0`;
* a single task score is clamped to ±0.5 of the miner's current EMA before it
  enters reputation, on top of the EMA damping itself.

### 2.12 Sample requirements
No emission below 10 scored tasks; reputation is shrunk toward a low prior below
20. Measured: 100 sybils with one perfect task each receive **0.0%** of
emissions while a single established honest miner takes **100%**.

---

## 3. Explicit assumptions

1. Validators are honest about *grading*. The commitment constrains this but
   does not yet prove it on chain.
2. Ground-truth generation is correct. Every generator self-verifies in tests,
   and reasoning tasks are brute-force checked for solution uniqueness before
   publication.
3. Deterministic verifiability is a feature boundary, not an oversight: tasks
   whose correctness cannot be checked programmatically are out of scope.
4. In `local_neurons` mode the archetype behaviours degrade a genuinely
   computed answer — they are a model of operator quality, not evidence about
   any AI system.

---

## 4. What would still break this

* **A genuinely superior model.** Intended: it should win.
* **A paraphrasing cartel.** Byte-identical evidence is detected; semantically
  identical but reworded evidence is not.
* **Subtle evidence stuffing.** Coverage is lexical. Gross stuffing is now
  caught by the outlier guard, but a miner that pads with plausible, varied,
  on-topic terms can still inflate this dimension. Entailment-based scoring is
  the intended replacement and is *not* implemented.
* **A compromised validator host.** Ground-truth confidentiality assumes the
  validator process is not readable by the attacker.
* **A model monoculture.** Correlated errors would inflate agreement, which is
  precisely why consensus is not used as truth for verifiable categories.
