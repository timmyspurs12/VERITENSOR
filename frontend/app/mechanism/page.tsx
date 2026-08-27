"use client";

import {
  Coins, Cpu, Gauge, Layers, Lock, Radar, Repeat, Scale, ShieldCheck, Workflow,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { PageHeader } from "@/components/shell";
import { Badge, Card, CardHeader, Label, LoadingRow, Meter } from "@/components/ui";
import { LoopDiagram } from "@/components/loop-diagram";
import { useMechanism, useStats } from "@/hooks/use-api";
import { num, pct } from "@/lib/format";

export default function MechanismPage() {
  const { data: cfg, isLoading } = useMechanism();
  const { data: stats } = useStats();
  const [confidence, setConfidence] = React.useState(0.95);
  const [hitRate, setHitRate] = React.useState(0.6);

  // Brier arithmetic mirrored from subnet/scoring/components.py
  const worst = cfg?.calibration?.worst_brier ?? 0.25;
  const brier = hitRate * (1 - confidence) ** 2 + (1 - hitRate) * confidence ** 2;
  const calibration = Math.max(0, Math.min(1, 1 - Math.min(brier, worst) / worst));

  return (
    <>
      <PageHeader
        title="How VERITENSOR prices trust"
        description="The mechanism, end to end, with the live configuration values the running subnet is using."
      />

      <Card className="mb-5">
        <CardHeader title="Why VERITENSOR?" subtitle="The gap this subnet fills" />
        <div className="grid gap-6 px-5 py-5 md:grid-cols-3">
          <Para title="AI output is abundant; verified AI output is not.">
            Anyone can generate a plausible answer. Establishing that an answer is
            correct still requires either a human or a deterministic checker, and
            neither scales with generation volume.
          </Para>
          <Para title="Static benchmarks decay into answer keys.">
            The moment a benchmark is public it measures recall. A verification
            network must generate its problems continuously and keep their
            solutions private.
          </Para>
          <Para title="Bittensor prices exactly this kind of work.">
            The subnet needs a scarce, objectively measurable output. “Answers that
            survive independent verification” is measurable, hard to fake, and
            useful to anybody deploying models in production.
          </Para>
        </div>
      </Card>

      <Card className="mb-5">
        <CardHeader title="The loop" subtitle="Validator → task → miner → verification → scoring → emissions" />
        <div className="p-5"><LoopDiagram /></div>
      </Card>

      <div className="mb-5 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Why miners compete" subtitle="The economic argument" />
          <div className="space-y-3 px-5 py-4 text-[13px] leading-relaxed text-ink-2">
            <p>
              Emission weight is a monotone function of reputation above a floor,
              sharpened by a temperature exponent of{" "}
              <span className="font-mono text-accent">{num(cfg?.emission?.temperature, 1)}</span>.
              A miner that improves its verified accuracy does not gain a linear
              amount of reward — it gains a superlinear amount, because the surplus
              above the floor is raised to that power before normalisation.
            </p>
            <p>
              At the same time the per-miner cap of{" "}
              <span className="font-mono text-accent">{pct(cfg?.emission?.max_share, 0)}</span>{" "}
              prevents a single dominant miner from absorbing the subnet, which keeps
              it worthwhile for new entrants to register.
            </p>
            <p className="text-ink-3">
              Net effect: better verified intelligence → higher reputation → higher
              emission weight → capital flows to the miners that are actually right.
            </p>
          </div>
        </Card>

        <Card>
          <CardHeader title="Why validators matter" subtitle="Integrity of the measurement" />
          <div className="space-y-3 px-5 py-4 text-[13px] leading-relaxed text-ink-2">
            <p>
              Validators are the only holders of ground truth. They commit to the
              hidden answer with an HMAC over (task id, nonce, answer) before
              dispatch, so they cannot retrofit an answer once responses arrive.
            </p>
            <p>
              Each validator runs an independent task engine, guard and scorer with
              a different strategy — coverage, probe rate and category mix all vary
              — so a miner cannot overfit to one evaluator&apos;s habits.
            </p>
            <p>
              Consensus is reported for observability but is deliberately{" "}
              <span className="text-ink-1">not</span> used as truth for
              programmatically verifiable categories. If a colluding majority could
              define correctness, the subnet would measure agreement, not accuracy.
            </p>
          </div>
        </Card>
      </div>

      {/* scoring */}
      <Card className="mb-5">
        <CardHeader title="Scoring formula" subtitle="Live weights from the running configuration" />
        {isLoading ? <LoadingRow /> : (
          <div className="grid gap-6 px-5 py-5 lg:grid-cols-2">
            <div>
              <pre className="overflow-x-auto rounded-md border border-line bg-bg px-4 py-3 font-mono text-xs leading-relaxed text-ink-2">
{`final_score =
    accuracy    × ${num(cfg?.weights?.accuracy, 2)}
  + evidence    × ${num(cfg?.weights?.evidence, 2)}
  + robustness  × ${num(cfg?.weights?.robustness, 2)}
  + calibration × ${num(cfg?.weights?.calibration, 2)}
  + latency     × ${num(cfg?.weights?.latency, 2)}
  , then × (1 − penalties)`}
              </pre>
              <div className="mt-4 space-y-2.5">
                {Object.entries(cfg?.weights ?? {}).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-3">
                    <span className="w-24 font-mono text-2xs uppercase tracking-wider text-ink-3">{k}</span>
                    <Meter value={Number(v)} />
                    <span className="w-12 text-right font-mono text-xs text-accent">{pct(Number(v), 0)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="space-y-3 text-[13px] leading-relaxed text-ink-2">
              <Item icon={ShieldCheck} title="Accuracy">
                Deterministic verifier output against hidden ground truth. Never an
                LLM judge: the same answer must always receive the same grade.
              </Item>
              <Item icon={Layers} title="Evidence quality">
                Coverage of generator-declared concepts (which miners never see),
                structural completeness and lexical specificity. Recognised
                boilerplate scores 0.05.
              </Item>
              <Item icon={Radar} title="Robustness">
                EMA over mutation probes. A conclusion that flips when variables are
                renamed was pattern matching, not verification.
              </Item>
              <Item icon={Scale} title="Calibration">
                Brier score over the last {cfg?.calibration?.window ?? 50} responses,
                normalised against a worst case of {num(worst, 2)}.
              </Item>
              <Item icon={Gauge} title="Latency">
                Full marks under {cfg?.latency?.target_ms ?? 1200} ms, decaying to a
                floor at {cfg?.latency?.timeout_ms ?? 15000} ms. Budget-based, so
                answering instantly and wrongly wins nothing.
              </Item>
            </div>
          </div>
        )}
      </Card>

      {/* calibration playground */}
      <Card className="mb-5">
        <CardHeader title="Calibration, interactively"
          subtitle="Move the sliders: this computes the exact Brier formula the backend uses." />
        <div className="grid gap-6 px-5 py-5 md:grid-cols-2">
          <div className="space-y-5">
            <Slider label="Stated confidence" value={confidence} onChange={setConfidence} />
            <Slider label="Actual hit rate" value={hitRate} onChange={setHitRate} />
            <p className="text-xs leading-relaxed text-ink-3">
              brier = p·(1 − c)² + (1 − p)·c² &nbsp;·&nbsp; calibration = 1 − min(brier, {num(worst, 2)}) / {num(worst, 2)}
            </p>
          </div>
          <div className="flex flex-col justify-center rounded-md border border-line bg-surface-2 px-5 py-5">
            <Label>Brier score</Label>
            <p className="font-mono text-xl text-ink-1">{num(brier, 4)}</p>
            <Label className="mt-4">Calibration component</Label>
            <p className={`font-mono text-[40px] leading-none ${calibration > 0.6 ? "text-positive" : calibration > 0.3 ? "text-warning" : "text-negative"}`}>
              {num(calibration, 3)}
            </p>
            <p className="mt-3 text-xs leading-relaxed text-ink-3">
              A miner claiming 95% while being right 60% of the time scores 0.000 on
              this dimension. Honest, discriminative confidence — high when right,
              low when unsure — is the only way to earn it.
            </p>
          </div>
        </div>
      </Card>

      {/* anti-gaming + difficulty */}
      <div className="mb-5 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Anti-gaming" subtitle="What each defence actually stops" />
          <div className="divide-y divide-line/60">
            {[[Lock, "Hidden ground truth", "Answers live only in the validator process. No public endpoint returns them for an open task; the admin reveal route refuses non-closed tasks."],
              [Repeat, "Dynamic generation", "Each task is drawn from one of 13 seeded generators, so the surface text is new every time."],
              [Radar, "Mutation probes", "A correct answer may be followed by a semantics-preserving variant. Consistency is 15% of the score."],
              [Workflow, "Replay protection", "A response is bound to one (task id, nonce, miner). Reuse is rejected before scoring, with a full-score penalty."],
              [Cpu, "Duplicate detection", "Repeated answer fingerprints on open-ended tasks and reused evidence bodies are penalised; enum answers are exempt up to a high threshold to avoid false positives."],
              [Coins, "Sample requirements", `No emission below ${cfg?.emission?.min_tasks ?? 10} scored tasks, and reputation is shrunk toward a prior below ${cfg?.reputation?.min_tasks_for_full_trust ?? 20} tasks.`],
            ].map(([Icon, t, d]: any) => (
              <div key={t} className="flex gap-3 px-5 py-3">
                <Icon size={14} className="mt-0.5 shrink-0 text-mint" />
                <div>
                  <p className="text-[13px] font-medium text-ink-1">{t}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-ink-3">{d}</p>
                </div>
              </div>
            ))}
          </div>
          <p className="border-t border-line px-5 py-3 text-xs leading-relaxed text-ink-3">
            Limitations are documented rather than hidden: none of these defeat a
            genuinely capable colluding cartel, and duplicate detection is a
            heuristic. See docs/ANTI_GAMING.md.
          </p>
        </Card>

        <Card>
          <CardHeader title="Adaptive difficulty" subtitle="Keeping the subnet in the informative band" />
          <div className="px-5 py-4">
            <div className="space-y-2">
              {[["score < " + num(cfg?.difficulty?.easy_below, 2), "Easy", "1–3", "#8FE3A9"],
                ["< " + num(cfg?.difficulty?.normal_below, 2), "Normal", "4–6", "#7DD6FA"],
                ["< " + num(cfg?.difficulty?.hard_below, 2), "Hard", "7–8", "#EFC468"],
                ["≥ " + num(cfg?.difficulty?.hard_below, 2), "Adversarial", "9–10", "#F27E88"],
              ].map(([cond, band, range, colour]) => (
                <div key={band as string} className="flex items-center gap-3 rounded-md border border-line bg-surface-2 px-3 py-2.5">
                  <span className="h-2 w-2 rounded-full" style={{ background: colour as string }} />
                  <span className="font-mono text-xs text-ink-3">{cond}</span>
                  <span className="text-[13px] text-ink-1">{band}</span>
                  <span className="ml-auto font-mono text-xs text-ink-2">difficulty {range}</span>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs leading-relaxed text-ink-3">
              The network is currently scoring{" "}
              <span className="font-mono text-accent">{num(stats?.network_score)}</span>,
              so validators with adaptive policies are drawing from the{" "}
              <span className="text-ink-1">
                {(stats?.network_score ?? 0) < (cfg?.difficulty?.easy_below ?? 0.6) ? "easy"
                  : (stats?.network_score ?? 0) < (cfg?.difficulty?.normal_below ?? 0.8) ? "normal"
                  : (stats?.network_score ?? 0) < (cfg?.difficulty?.hard_below ?? 0.9) ? "hard" : "adversarial"}
              </span>{" "}
              band. Thresholds are configuration, not constants in the code.
            </p>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Why this becomes a marketplace" subtitle="Beyond the hackathon" />
        <div className="grid gap-6 px-5 py-5 md:grid-cols-3">
          <Para title="Verification is a measurable commodity.">
            A reputation number backed by thousands of independently graded,
            mutation-tested tasks is a price signal for reliability — something no
            public leaderboard currently provides.
          </Para>
          <Para title="Demand exists outside the subnet.">
            Any team shipping model output into production needs an answer to
            &ldquo;how often is this right, and does it know when it is not?&rdquo;
            The same pipeline can grade externally submitted claims.
          </Para>
          <Para title="The mechanism scales with new families.">
            Adding a verifiable domain means writing one generator plus one
            deterministic verifier. The scoring, reputation and emission machinery
            is unchanged.
          </Para>
        </div>
        <div className="flex flex-wrap gap-3 border-t border-line px-5 py-4">
          <Link href="/simulation">
            <Badge tone="accent">Run the mechanism yourself →</Badge>
          </Link>
          <Link href="/scores"><Badge>Inspect a score →</Badge></Link>
          <Link href="/emissions"><Badge>See the weight vector →</Badge></Link>
        </div>
      </Card>
    </>
  );
}

function Para({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-ink-1">{title}</h3>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{children}</p>
    </div>
  );
}

function Item({ icon: Icon, title, children }: { icon: any; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <Icon size={14} className="mt-0.5 shrink-0 text-accent" />
      <div>
        <p className="text-[13px] font-medium text-ink-1">{title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-ink-3">{children}</p>
      </div>
    </div>
  );
}

function Slider({ label, value, onChange }: {
  label: string; value: number; onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <Label>{label}</Label>
        <span className="font-mono text-sm text-ink-1">{pct(value, 0)}</span>
      </div>
      <input type="range" min={0} max={1} step={0.01} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full accent-[#7DD6FA]" />
    </div>
  );
}
