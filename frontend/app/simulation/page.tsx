"use client";

import { AlertTriangle, ArrowDown, ArrowUp, Cpu, Play, RotateCw, Timer } from "lucide-react";
import * as React from "react";
import { PageHeader } from "@/components/shell";
import {
  Badge, Button, Card, CardHeader, EmptyState, Label, Meter, SegmentedControl,
  Stat, Table, Td, Th,
} from "@/components/ui";
import { BarSeries, TrendChart } from "@/components/charts";
import { EventFeed } from "@/components/event-feed";
import { api } from "@/lib/api";
import { categoryLabel, ms, num, pct } from "@/lib/format";
import type { SimulationResult } from "@/types";

const PIPELINE = ["Populate network", "Generate tasks", "Dispatch to miners",
  "Verify responses", "Adversarial probes", "Score & smooth", "Recompute emissions"];

export default function SimulationPage() {
  const [miners, setMiners] = React.useState("10");
  const [validators, setValidators] = React.useState("3");
  const [tasks, setTasks] = React.useState("50");
  const [difficulty, setDifficulty] = React.useState("adaptive");
  const [seed, setSeed] = React.useState("");
  const [running, setRunning] = React.useState(false);
  const [stage, setStage] = React.useState(-1);
  const [result, setResult] = React.useState<SimulationResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const run = async () => {
    setRunning(true); setError(null); setResult(null); setStage(0);
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, PIPELINE.length - 2)), 420);
    try {
      const res = await api.runSimulation({
        miners: Number(miners), validators: Number(validators), tasks: Number(tasks),
        difficulty, seed: seed ? Number(seed) : undefined,
      });
      setResult(res);
      setStage(PIPELINE.length - 1);
    } catch (e) {
      setError(String(e));
      setStage(-1);
    } finally {
      clearInterval(timer);
      setRunning(false);
    }
  };

  const epochSeries = (result?.epochs ?? []).map((e) => ({
    epoch: `E${e.epoch}`, accuracy: e.network_accuracy, score: e.network_score,
  }));

  return (
    <>
      <PageHeader
        title="Network simulation"
        description="Spin up an isolated subnet — fresh miners, fresh validators, fresh task history — and execute the real pipeline. Results are computed by the backend, not sampled from the seeded network."
      />

      <Card>
        <CardHeader title="Configuration" subtitle="Bounded server-side: max 60 miners, 7 validators, 400 tasks per run" />
        <div className="grid gap-5 px-5 py-5 md:grid-cols-2 xl:grid-cols-4">
          <Field label="Miners">
            <SegmentedControl value={miners} onChange={setMiners}
              options={[{ value: "5", label: "5" }, { value: "10", label: "10" },
                { value: "25", label: "25" }, { value: "50", label: "50" }]} />
          </Field>
          <Field label="Validators">
            <SegmentedControl value={validators} onChange={setValidators}
              options={[{ value: "1", label: "1" }, { value: "3", label: "3" }, { value: "5", label: "5" }]} />
          </Field>
          <Field label="Tasks">
            <SegmentedControl value={tasks} onChange={setTasks}
              options={[{ value: "10", label: "10" }, { value: "50", label: "50" },
                { value: "100", label: "100" }, { value: "200", label: "200" }]} />
          </Field>
          <Field label="Difficulty">
            <SegmentedControl value={difficulty} onChange={setDifficulty}
              options={[{ value: "easy", label: "Easy" }, { value: "normal", label: "Normal" },
                { value: "hard", label: "Hard" }, { value: "adaptive", label: "Adaptive" }]} />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-4">
          <label className="flex items-center gap-2">
            <Label>Seed (optional)</Label>
            <input value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))}
              placeholder="deterministic"
              className="w-32 rounded-sm border border-line-strong bg-surface-2 px-2 py-1.5 font-mono text-xs text-ink-1 outline-none focus:border-accent/50" />
          </label>
          <Button variant="primary" size="lg" onClick={run} disabled={running} className="ml-auto">
            {running ? <RotateCw size={14} className="animate-spin" /> : <Play size={14} />}
            {running ? "Running simulation…" : "RUN NETWORK SIMULATION"}
          </Button>
        </div>
      </Card>

      {(running || result) && (
        <Card className="mt-4">
          <CardHeader title="Pipeline" subtitle="Stages executed by the backend for this run" />
          <div className="flex flex-wrap items-center gap-2 px-5 py-4">
            {PIPELINE.map((p, i) => {
              const done = stage >= i;
              return (
                <React.Fragment key={p}>
                  <div className={`rounded-sm border px-2.5 py-1.5 font-mono text-2xs uppercase tracking-[0.1em] transition-colors ${
                    done ? "border-accent/35 bg-accent/10 text-accent"
                         : "border-line bg-surface-2 text-ink-3"}`}>
                    {p}
                  </div>
                  {i < PIPELINE.length - 1 && <span className="text-line-hi">→</span>}
                </React.Fragment>
              );
            })}
          </div>
        </Card>
      )}

      {error && (
        <div className="mt-4 flex items-center gap-2 rounded-md border border-negative/30 bg-negative/[0.07] px-4 py-3 text-[13px] text-negative">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {!result && !running && (
        <Card className="mt-4">
          <EmptyState title="No simulation run yet"
            description="Choose a configuration and run it. Nothing on this page is pre-filled: the tables below stay empty until the backend returns real results." />
        </Card>
      )}

      {result && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-5">
            <Card className="rounded-none border-0">
              <Stat label="Tasks completed" value={result.tasks_completed}
                hint={`${result.config.miners} miners · ${result.config.validators} validators`} />
            </Card>
            <Card className="rounded-none border-0">
              <Stat label="Network accuracy" tone="accent" value={pct(result.stats.network_accuracy)}
                hint={`mean score ${num(result.stats.mean_task_score)}`} />
            </Card>
            <Card className="rounded-none border-0">
              <Stat label="Mean latency" value={ms(result.stats.mean_latency_ms)}
                hint={`p95 ${ms(result.stats.p95_latency_ms)}`} />
            </Card>
            <Card className="rounded-none border-0">
              <Stat label="Adversarial probes" value={result.adversarial.probes}
                tone={result.adversarial.hold_rate > 0.7 ? "positive" : "warning"}
                hint={`${pct(result.adversarial.hold_rate)} held · ${result.adversarial.flipped} flipped`} />
            </Card>
            <Card className="rounded-none border-0">
              <Stat label="Wall clock" value={`${result.wall_clock_seconds}s`} tone="warning"
                hint={`${result.stats.rejected_responses} rejected responses`} />
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="Miner ranking after the run"
                subtitle="Reputation, emission share and rank movement inside this isolated network" />
              <Table>
                <thead>
                  <tr>
                    <Th>#</Th><Th>Miner</Th><Th>Archetype</Th><Th align="right">Reputation</Th>
                    <Th align="right">Accuracy</Th><Th align="right">Tasks</Th>
                    <Th align="right">Emission</Th><Th align="right">Δ rank</Th>
                  </tr>
                </thead>
                <tbody>
                  {result.leaderboard.map((m) => {
                    const change = result.rank_changes.find((c) => c.uid === m.uid);
                    return (
                      <tr key={m.uid} className="hover:bg-surface-2/60">
                        <Td className="font-mono text-ink-3">{m.rank}</Td>
                        <Td className="text-ink-1">{m.name}</Td>
                        <Td><span className="text-xs text-ink-3">{m.profile_label}</span></Td>
                        <Td align="right">
                          <div className="flex items-center justify-end gap-2">
                            <span className="font-mono">{num(m.reputation)}</span>
                            <Meter value={m.reputation} className="w-10" />
                          </div>
                        </Td>
                        <Td align="right">{pct(m.accuracy)}</Td>
                        <Td align="right">{m.task_count}</Td>
                        <Td align="right" className="font-mono text-accent">{pct(m.emission_weight, 2)}</Td>
                        <Td align="right">
                          {!change || change.delta === 0 ? <span className="text-ink-3">—</span>
                            : change.delta > 0
                              ? <span className="inline-flex items-center gap-1 text-positive"><ArrowUp size={11} />{change.delta}</span>
                              : <span className="inline-flex items-center gap-1 text-negative"><ArrowDown size={11} />{Math.abs(change.delta)}</span>}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </Card>

            <div className="space-y-4">
              <Card>
                <CardHeader title="Emission distribution" subtitle="Normalised weights from this run" />
                <div className="p-4">
                  <BarSeries height={200}
                    data={result.leaderboard.slice(0, 12).map((m) => ({
                      name: m.name.split("-")[0], weight: m.emission_weight,
                      fill: m.emission_weight > 0 ? "#7DD6FA" : "#2A323D" }))}
                    xKey="name" yKey="weight" colorKey="fill"
                    format={(v) => `${(v * 100).toFixed(0)}%`} />
                </div>
              </Card>
              <Card>
                <CardHeader title="Accuracy by epoch" subtitle="Within this simulated network" />
                <div className="p-4">
                  <TrendChart data={epochSeries} xKey="epoch" height={180} domain={[0, 1]}
                    format={(v) => `${(v * 100).toFixed(0)}%`}
                    series={[{ key: "accuracy", label: "Accuracy", color: "#7DD6FA" },
                      { key: "score", label: "Reputation", color: "#A8F0C6" }]} />
                </div>
              </Card>
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader title="Task families" subtitle="Volume and accuracy in this run" />
              <Table>
                <thead><tr><Th>Family</Th><Th align="right">Tasks</Th><Th align="right">Accuracy</Th><Th align="right">Mean diff</Th></tr></thead>
                <tbody>
                  {result.categories.map((c) => (
                    <tr key={c.category}>
                      <Td className="text-ink-1">{categoryLabel[c.category]}</Td>
                      <Td align="right">{c.tasks}</Td>
                      <Td align="right">{pct(c.accuracy)}</Td>
                      <Td align="right">{num(c.mean_difficulty, 1)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>

            <Card>
              <CardHeader title="Robustness by miner" subtitle="Mutation probes held vs issued" />
              <Table>
                <thead><tr><Th>Miner</Th><Th align="right">Probes</Th><Th align="right">Held</Th><Th align="right">Rate</Th></tr></thead>
                <tbody>
                  {Object.entries(result.adversarial.by_miner).map(([uid, v]) => {
                    const miner = result.leaderboard.find((m) => String(m.uid) === uid);
                    return (
                      <tr key={uid}>
                        <Td className="text-ink-1">{miner?.name ?? `uid ${uid}`}</Td>
                        <Td align="right">{v.probes}</Td>
                        <Td align="right">{v.held}</Td>
                        <Td align="right" className={v.held / v.probes > 0.7 ? "text-positive" : "text-warning"}>
                          {pct(v.held / v.probes, 0)}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </Card>

            <Card>
              <CardHeader title="Run event log" subtitle="Last events emitted by this simulation" />
              <div className="max-h-[340px] overflow-y-auto">
                <EventFeed events={[...result.events].reverse()} limit={60} compact />
              </div>
            </Card>
          </div>
        </>
      )}
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      <div className="mt-2">{children}</div>
    </div>
  );
}
