import Link from "next/link";
import {
  ArrowRight, Boxes, Cpu, Eye, GitBranch, Layers, Lock, Radar, Repeat,
  ShieldCheck, Sparkles, Workflow,
} from "lucide-react";
import { Badge, Card, Label } from "@/components/ui";
import { Wordmark } from "@/components/wordmark";
import { LoopDiagram } from "@/components/loop-diagram";

const PROBLEMS = [
  {
    title: "Generation is cheap. Verification is not.",
    body: "Model output is abundant and nearly free. Determining whether a given answer is actually correct still costs human review, and it does not scale with the volume of machine-generated claims.",
  },
  {
    title: "Benchmarks leak, then die.",
    body: "A static benchmark is a public answer key. Once it circulates it measures memorisation, not capability, and the leaderboard it produces is no longer informative.",
  },
  {
    title: "Confidence is unpriced.",
    body: "A model that is right 60% of the time while claiming 95% certainty is more dangerous than one that admits uncertainty. Nothing in today's stack charges for that miscalibration.",
  },
];

const PILLARS = [
  { icon: Layers, title: "Dynamically generated tasks",
    body: "Four verifiable families — code security, mathematics, logical reasoning, data analysis — generated from random seeds with ground truth computed at generation time. 13 generators, no static answer key." },
  { icon: ShieldCheck, title: "Independent validation",
    body: "Validators grade with deterministic verifiers, never with another language model. The same answer always receives the same score, and any judge can re-run it." },
  { icon: Radar, title: "Adversarial robustness probes",
    body: "After a correct answer a validator may issue a semantics-preserving mutation of the same problem. A conclusion that flips under renaming was never knowledge." },
  { icon: Repeat, title: "Calibration is scored",
    body: "Stated confidence is graded with a Brier score over a rolling window. Persistent overconfidence costs emission weight." },
];

const ARCHITECTURE = [
  { label: "subnet/protocol", body: "Task + response wire types. Ground truth is structurally absent from every miner-facing message." },
  { label: "subnet/tasks", body: "Generators, mutation engine and deterministic verifiers. Ground truth is computed, not written." },
  { label: "subnet/miner", body: "Pluggable model backends plus nine behavioural profiles for the local simulation." },
  { label: "subnet/validator", body: "The pipeline: generate → dispatch → validate → score → probe → reputation → emissions." },
  { label: "subnet/scoring", body: "Weighted scoring, Brier calibration, EMA reputation, emission normalisation, anti-gaming detectors." },
  { label: "subnet/adapters", body: "One interface, two implementations: SimulationAdapter today, BittensorAdapter for testnet." },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-bg">
      {/* nav */}
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1180px] items-center gap-4 px-5">
          <Wordmark />
          <nav className="ml-auto hidden items-center gap-1 text-[13px] text-ink-2 md:flex">
            {[["Mechanism", "/mechanism"], ["Dashboard", "/dashboard"],
              ["Simulation", "/simulation"], ["Tasks", "/tasks"]].map(([label, href]) => (
              <Link key={href} href={href}
                className="rounded-sm px-3 py-1.5 transition-colors hover:bg-surface-2 hover:text-ink-1">
                {label}
              </Link>
            ))}
          </nav>
          <Link href="/demo"
            className="ml-auto flex items-center gap-1.5 rounded-sm border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 md:ml-0">
            <Sparkles size={13} /> Run demo
          </Link>
        </div>
      </header>

      {/* hero */}
      <section className="relative overflow-hidden border-b border-line">
        <div className="grid-field absolute inset-0" />
        <div className="relative mx-auto max-w-[1180px] px-5 py-20 md:py-28">
          <Badge tone="accent" className="mb-6">
            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent" />
            Bittensor Global Subnet Hackathon 2026
          </Badge>
          <h1 className="max-w-3xl text-[38px] font-semibold leading-[1.08] tracking-[-0.02em] text-ink-1 md:text-[56px]">
            The decentralized verification layer for machine intelligence.
          </h1>
          <p className="mt-6 max-w-2xl text-[15px] leading-relaxed text-ink-2 md:text-base">
            Miners compete to produce reliable AI answers. Validators independently
            verify them. Performance determines reputation and emission.
          </p>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-3">
            VERITENSOR does not reward miners for producing output. It rewards
            output that survives independent verification.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link href="/simulation"
              className="flex items-center gap-2 rounded-sm border border-accent/40 bg-accent/15 px-5 py-2.5 text-sm font-medium text-accent transition-colors hover:bg-accent/25">
              Run network demo <ArrowRight size={15} />
            </Link>
            <Link href="/mechanism"
              className="flex items-center gap-2 rounded-sm border border-line-strong bg-surface-2 px-5 py-2.5 text-sm text-ink-1 transition-colors hover:border-line-hi">
              Explore mechanism
            </Link>
          </div>

          <div className="mt-14 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-4">
            {[["4", "verifiable task families"], ["13", "task generators"],
              ["5", "scored dimensions"], ["9", "miner archetypes"]].map(([v, l]) => (
              <div key={l} className="bg-surface-1 px-5 py-4">
                <p className="font-mono text-[24px] text-accent">{v}</p>
                <p className="mt-1 text-xs text-ink-3">{l}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* problem */}
      <section className="border-b border-line">
        <div className="mx-auto max-w-[1180px] px-5 py-16 md:py-20">
          <Label>01 — Problem</Label>
          <h2 className="mt-3 max-w-2xl text-[28px] font-semibold leading-tight tracking-tight md:text-[34px]">
            Nobody is paid to be reliably right.
          </h2>
          <div className="mt-9 grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-3">
            {PROBLEMS.map((p) => (
              <div key={p.title} className="bg-surface-1 p-6">
                <h3 className="text-sm font-semibold text-ink-1">{p.title}</h3>
                <p className="mt-2.5 text-[13px] leading-relaxed text-ink-2">{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* solution */}
      <section className="border-b border-line bg-bg-subtle">
        <div className="mx-auto max-w-[1180px] px-5 py-16 md:py-20">
          <Label>02 — Solution</Label>
          <h2 className="mt-3 max-w-2xl text-[28px] font-semibold leading-tight tracking-tight md:text-[34px]">
            Turn verification itself into the commodity.
          </h2>
          <p className="mt-4 max-w-2xl text-[13px] leading-relaxed text-ink-2">
            A validator generates a task whose answer it already knows but has never
            published. Miners answer. The validator grades correctness, evidence,
            robustness under mutation, confidence calibration and latency, then
            converts the result into a normalised emission weight.
          </p>
          <div className="mt-9 grid gap-4 md:grid-cols-2">
            {PILLARS.map((p) => (
              <Card key={p.title} className="p-6">
                <div className="flex items-start gap-4">
                  <div className="rounded-md border border-line-strong bg-surface-2 p-2.5">
                    <p.icon size={16} className="text-accent" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-ink-1">{p.title}</h3>
                    <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{p.body}</p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* loop */}
      <section className="border-b border-line">
        <div className="mx-auto max-w-[1180px] px-5 py-16 md:py-20">
          <Label>03 — The loop</Label>
          <h2 className="mt-3 text-[28px] font-semibold leading-tight tracking-tight md:text-[34px]">
            Task → miners → verification → reputation → emissions.
          </h2>
          <div className="mt-9"><LoopDiagram /></div>
        </div>
      </section>

      {/* miners / validators */}
      <section className="border-b border-line bg-bg-subtle">
        <div className="mx-auto grid max-w-[1180px] gap-4 px-5 py-16 md:grid-cols-2 md:py-20">
          <Card className="p-6">
            <div className="flex items-center gap-2.5">
              <Cpu size={15} className="text-accent" />
              <h3 className="text-sm font-semibold">How miners work</h3>
            </div>
            <ol className="mt-4 space-y-3 text-[13px] leading-relaxed text-ink-2">
              <li><span className="font-mono text-2xs text-ink-3">01</span> Receive a task request containing only prompt, category, difficulty, nonce and deadline.</li>
              <li><span className="font-mono text-2xs text-ink-3">02</span> Solve it with any backend — a local model, an OpenAI-compatible endpoint, or a bespoke solver.</li>
              <li><span className="font-mono text-2xs text-ink-3">03</span> Return an answer, a calibrated confidence, evidence and execution time, echoing the nonce.</li>
              <li><span className="font-mono text-2xs text-ink-3">04</span> Expect a mutated follow-up at any time; consistency is scored, not just correctness.</li>
            </ol>
          </Card>
          <Card className="p-6">
            <div className="flex items-center gap-2.5">
              <ShieldCheck size={15} className="text-mint" />
              <h3 className="text-sm font-semibold">How validators work</h3>
            </div>
            <ol className="mt-4 space-y-3 text-[13px] leading-relaxed text-ink-2">
              <li><span className="font-mono text-2xs text-ink-3">01</span> Generate a task and commit to its hidden answer with an HMAC commitment.</li>
              <li><span className="font-mono text-2xs text-ink-3">02</span> Dispatch to a strategy-defined subset of miners and enforce nonce, deadline and rate limits.</li>
              <li><span className="font-mono text-2xs text-ink-3">03</span> Grade every response deterministically and probe robustness with mutations.</li>
              <li><span className="font-mono text-2xs text-ink-3">04</span> Smooth scores into reputation and publish normalised weights that sum to one.</li>
            </ol>
          </Card>
        </div>
      </section>

      {/* scoring + anti-gaming */}
      <section className="border-b border-line">
        <div className="mx-auto max-w-[1180px] px-5 py-16 md:py-20">
          <div className="grid gap-10 md:grid-cols-2">
            <div>
              <Label>04 — Scoring</Label>
              <h3 className="mt-3 text-[22px] font-semibold tracking-tight">Five dimensions, one weight vector.</h3>
              <div className="mt-5 overflow-hidden rounded-lg border border-line">
                {[["Accuracy", "45%", "Deterministic verification against hidden ground truth"],
                  ["Evidence quality", "20%", "Concept coverage, structure and specificity"],
                  ["Robustness", "15%", "Consistency under semantics-preserving mutation"],
                  ["Calibration", "10%", "Brier score of stated confidence vs outcomes"],
                  ["Latency", "10%", "Budget-based, never a race to the bottom"]].map(([n, w, d]) => (
                  <div key={n} className="flex items-baseline gap-4 border-b border-line px-4 py-3 last:border-0">
                    <span className="font-mono text-xs text-accent">{w}</span>
                    <div>
                      <p className="text-[13px] text-ink-1">{n}</p>
                      <p className="text-xs text-ink-3">{d}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <Label>05 — Anti-gaming</Label>
              <h3 className="mt-3 text-[22px] font-semibold tracking-tight">Memorisation is not a strategy.</h3>
              <ul className="mt-5 space-y-3">
                {[[Lock, "Hidden ground truth", "Answers exist only inside the validator boundary; no API path returns them for an open task."],
                  [GitBranch, "Dynamic generation + mutation", "Every task is drawn from a seeded generator, then optionally mutated into a variant with the same answer."],
                  [Eye, "Duplicate & collusion detection", "Repeated answer fingerprints and byte-identical reasoning across miners are flagged and penalised."],
                  [Workflow, "Replay protection", "A response is bound to one task id and nonce; reuse is rejected before scoring."]].map(([Icon, t, d]: any) => (
                  <li key={t} className="flex gap-3">
                    <Icon size={15} className="mt-0.5 shrink-0 text-mint" />
                    <div>
                      <p className="text-[13px] font-medium text-ink-1">{t}</p>
                      <p className="text-xs leading-relaxed text-ink-3">{d}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* architecture */}
      <section className="border-b border-line bg-bg-subtle">
        <div className="mx-auto max-w-[1180px] px-5 py-16 md:py-20">
          <Label>06 — Architecture</Label>
          <h2 className="mt-3 text-[28px] font-semibold leading-tight tracking-tight md:text-[34px]">
            Readable by a subnet engineer, not just a judge.
          </h2>
          <div className="mt-8 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            {ARCHITECTURE.map((a) => (
              <div key={a.label} className="bg-surface-1 p-5">
                <p className="font-mono text-xs text-accent">{a.label}</p>
                <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{a.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* roadmap */}
      <section className="border-b border-line">
        <div className="mx-auto max-w-[1180px] px-5 py-16 md:py-20">
          <Label>07 — Roadmap</Label>
          <div className="mt-8 grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-4">
            {[["Now", "Local subnet prototype", "Full pipeline, 13 generators, deterministic scoring, emissions and 120 automated tests."],
              ["Next", "Testnet registration", "Wire the BittensorAdapter to a funded testnet hotkey and publish weights on chain."],
              ["Then", "Commit–reveal on chain", "Publish the task commitment on chain before dispatch so grading is externally auditable."],
              ["Later", "Verification marketplace", "External clients submit claims for verification and pay for a scored, evidenced verdict."],
            ].map(([when, title, body]) => (
              <div key={title} className="bg-surface-1 p-5">
                <span className="font-mono text-2xs uppercase tracking-[0.14em] text-accent">{when}</span>
                <p className="mt-2 text-sm font-medium text-ink-1">{title}</p>
                <p className="mt-2 text-xs leading-relaxed text-ink-3">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-4 px-5 py-10 text-xs text-ink-3">
        <Wordmark compact />
        <span>VERITENSOR — decentralized AI verification subnet prototype.</span>
        <span className="ml-auto">
          Independent hackathon project. Not affiliated with or endorsed by the Opentensor Foundation.
        </span>
      </footer>
    </div>
  );
}
