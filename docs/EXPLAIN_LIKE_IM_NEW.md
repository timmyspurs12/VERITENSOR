# VERITENSOR explained, in plain language

Written for a hackathon judge, a teammate, or you at 2am before the pitch.
No jargon that isn't defined on the spot.

---

## 1. The one-sentence version

**VERITENSOR is a marketplace where AI systems compete to give answers that can
be independently proven correct, and the ones that prove it most reliably get
paid the most.**

---

## 2. The problem, without jargon

AI can write you an answer to almost anything, instantly and nearly free.

What it *can't* do is tell you, reliably, whether that answer is right.

Three specific things are broken:

1. **Checking is expensive.** Generating a million answers costs pennies.
   Checking a million answers still needs a human or a purpose-built test.
2. **Public tests stop working.** The moment a set of test questions is
   published, systems can memorise the answers. The scoreboard then measures
   memory, not ability — like an exam where the answer key leaked.
3. **Nobody is penalised for false confidence.** A model that is right 60% of
   the time while *insisting* it's 95% sure is genuinely dangerous, and today
   nothing charges it for that.

## 3. What VERITENSOR does about it

Think of it as a **continuous, un-leakable exam with prize money.**

* **Examiners** (called *validators*) write fresh questions constantly. Each
  question is generated from random numbers, so it has never existed before and
  can't have been memorised.
* Crucially, the examiner **works out the correct answer at the moment it
  writes the question** — by actually running the code, doing the arithmetic,
  or searching the possibilities. So the right answer is known for certain, and
  it is never published.
* **Candidates** (called *miners*) receive only the question. They send back an
  answer, how confident they are, and their reasoning.
* The examiner marks them, ranks them, and **money flows to the top of the
  ranking**.

That's the whole idea. The interesting part is *how* the marking works.

## 4. How marking works — five things, not one

Most benchmarks give one number: how often you were right. VERITENSOR scores
five, because "right" alone is easy to fake.

| What's measured | Weight | Why it exists |
| --- | --- | --- |
| **Correctness** | 45% | Was the answer actually right? Checked by a program, not an opinion. |
| **Evidence** | 20% | Did you show working that mentions the concepts that actually matter? |
| **Robustness** | 15% | If we rename the variables and ask again, do you still say the same thing? |
| **Calibration** | 10% | When you say "95% sure", are you right 95% of the time? |
| **Speed** | 10% | Answered within a sensible time budget. |

### The two clever ones

**Robustness.** After you get a question right, the examiner sometimes rewrites
the *same* problem — different variable names, shuffled sentences, reordered
data — and asks again. The correct answer is provably unchanged. If your answer
flips, you were pattern-matching, not understanding. You lose points.

**Calibration.** This is the one judges tend to like most. If you always claim
95% confidence but are only right 60% of the time, your calibration score is
**zero** — measured, not estimated. The only way to earn those points is to be
confident when you're right and hesitant when you're not. *We are paying models
to know what they don't know.*

## 5. How the money is shared out

Scores become "emission weights" — each miner's slice of the reward pie. Rules
that stop obvious cheats:

* **You need a track record.** Fewer than 10 answered questions and you get
  nothing. One lucky answer can't make you rich.
* **Slow-moving reputation.** Your score is a rolling average, so a single
  brilliant (or terrible) day barely moves it.
* **A floor.** Perform near guesswork and you earn zero — the network doesn't
  subsidise noise.
* **A ceiling.** No single participant can take more than ~25%, so newcomers
  always have a reason to join.
* **The slices always add to exactly 100%.** Never 99.9%, never 100.1%. This is
  enforced in code and verified by tests, because on a real blockchain a
  malformed number is a live bug.

## 6. Does it actually work? Yes — and here's the proof

We built nine "personality types" of AI participant and ran them through the
real system. We didn't type the results in — the software produced them:

| Personality | What it does | What it earned |
| --- | --- | --- |
| High-quality | Slow but careful and honest | **Top of the table** |
| Balanced / Fast | Solid all-rounders | Middle, healthy share |
| Hallucinating | Right ~54% of the time, always claims certainty | **~0.3%** |
| Gaming | Copy-pastes the same waffle every time | **0.0%** |

The hallucinating one is the headline: **more than half its answers are
correct, and it still earns almost nothing**, because it lies about how sure it
is. That is the mechanism doing exactly what it was designed to do.

We also attacked our own system 29 different ways (memorising, replaying old
answers, fake confidence, sock-puppet accounts, a colluding gang controlling
the majority). Every attack is a test that runs on every build. Sample results:

* 100 fake accounts each with one perfect answer → **0% of the rewards**
* A gang controlling 6 of 10 participants → honest ones still took **89%**
* Replaying a valid answer for a different question → **rejected before marking**

## 7. What's actually been built (the honest inventory)

**Working, running, tested today:**

* The question factory — 13 generators across code security, maths, logic and
  data analysis, plus a private hidden question bank.
* The marking engine, reputation system and reward maths.
* **Two real programs** — a miner and a validator — that run as separate
  processes and talk to each other over the network, authenticated with real
  Bittensor cryptographic keys. We ran 10 miners and 3 validators at once.
* A genuine solver: our reference miner *actually answers* the questions (~99%
  correct) by executing code and doing real maths. It isn't fed the answers.
* A web dashboard: live leaderboard, per-question breakdowns, a "why did this
  participant get this score" page, and a one-click full demo.
* 213 automated tests plus 10 frontend tests.
* An evidence trail: every question, answer, score and reward is written to a
  timestamped log file so a judge can check our claims instead of trusting them.

**Explicitly NOT done:**

* **It is not live on the Bittensor blockchain.** We can *read* the live test
  network (we verified it — we can see the current block number and browse
  existing subnets), but we have not registered on it or paid out real rewards.
  That requires real tokens and a funded wallet, which is a human decision, not
  a coding task.
* Our "personality types" are simulated behaviours, not real competing AI
  companies.
* The evidence-quality score looks for the right *words*, not the right
  *meaning*. A sophisticated participant could pad it.

Every one of these is written down in the repo. **Nothing in the dashboard
claims to be on a blockchain when it isn't** — there's a permanent banner
saying which mode you're in, and it's driven by the server, not a setting.

## 8. What "Bittensor" is and why it matters here

Bittensor is a blockchain that pays people for useful AI work. It's split into
"subnets" — each one is a mini-economy for a specific job (one for text
generation, one for image models, and so on). Each subnet decides its own rules
for who deserves payment.

VERITENSOR is a proposed subnet whose job is **verification**. It's a good fit
because Bittensor needs work that can be measured objectively and can't be
faked — and "did this answer survive an independent check?" is exactly that.

## 9. What's needed to make it production-ready

Grouped by honesty, not optimism.

### A. To go live on the test blockchain — days, needs money
1. Create a wallet and fund it with test tokens (free faucet).
2. Pick or create a subnet, register 10 miner + 3 validator identities. **Each
   registration costs tokens.**
3. Flip one config file to testnet mode and start the same programs.
   *The code for this is finished and waiting — see `docs/DEPLOYMENT_CHECKLIST.md`.*

### B. Real engineering gaps — weeks
4. **Real AI participants.** Today the reference miner is a rule-based solver.
   Production needs actual language models competing, which costs money per
   question.
5. **Smarter evidence checking.** Replace keyword-matching with something that
   verifies the reasoning genuinely supports the answer.
6. **Publish the commitment on-chain.** We already lock in the correct answer
   before asking, so the examiner can't cheat — but that lock currently lives on
   our own server. On a blockchain it should be public.
7. **Shared rate limiting.** Our abuse protection works per-server; running
   several servers needs a shared one (Redis).
8. **Proper database history.** Today the live state is in memory and the
   database is a mirror; production wants full replayable history.

### C. Operational maturity — ongoing
9. Monitoring and alerting; on-call for validators (they must never go silent).
10. Security review by someone who didn't write it.
11. More question types — the subnet is only as useful as the range of things it
    can verify.
12. Cost modelling: what does one verification cost, and what is it worth?

### D. The strategic question — the real one
13. **Who pays for verification, and why?** Today rewards come from the subnet's
    token emissions. The long-term case is that outside customers pay to have
    their AI outputs verified. That's a business hypothesis, not a technical
    one, and it's the thing to be most honest about in a pitch.

## 10. If a judge asks one hard question, it'll be this

> *"Your questions are auto-generated puzzles. Does doing well here mean
> anything in the real world?"*

The honest answer: **not by itself, yet.** What VERITENSOR proves today is that
the *mechanism* works — that you can rank AI systems on verifiable work,
detect and defund the ones that bluff, and do it without a leakable answer key.
The question categories are deliberately narrow because they're the ones that
can be checked with certainty. Broadening them, without giving up that
certainty, is the roadmap.

That answer is better than overclaiming, and it's the same answer the code,
the docs and the dashboard all give.
