"use client";

import {
  ArrowDown, ArrowUp, CircleCheck, CircleX, PlayCircle, Radar, RotateCw,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { PageHeader } from "@/components/shell";
import {
  Badge, Button, Card, CardHeader, EmptyState, Label, Meter, Stat, Table, Td, Th,
} from "@/components/ui";
import { EventFeed } from "@/components/event-feed";
import { api } from "@/lib/api";
import { categoryLabel, ms, num, pct } from "@/lib/format";
import type { DemoResult } from "@/types";

export default function DemoPage() {
  const [result, setResult] = React.useState<DemoResult | null>(null);
  const [running, setRunning] = React.useState(false);
  const [visible, setVisible] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);

  const run = async () => {
    setRunning(true); setError(null); setResult(null); setVisible(0);
    try {
      const res = await api.runDemo();
      setResult(res);
      // reveal the stages the backend actually executed, one at a time
      res.stages.forEach((_, i) => setTimeout(() => setVisible(i + 1), 380 * (i + 1)));
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const scored = result?.task.responses.filter((r) => !r.rejected) ?? [];
  const movers = (result?.movements ?? []).filter((m) => m.delta !== 0).slice(0, 6);

  return (
    <>
      <PageHeader
        title="Hackathon demo"
        description="One button, one task, the entire incentive loop: generate → dispatch → answer → verify → mutate → score → reputation → emissions → leaderboard. Everything below is produced by the backend during this run."
        actions={
          <Button variant="primary" size="lg" onClick={run} disabled={running}>
            {running ? <RotateCw size={15} className="animate-spin" /> : <PlayCircle size={15} />}
            {running ? "Running…" : "RUN FULL DEMO"}
          </Button>
        }
      />

      {error && (
        <div className="mb-4 rounded-md border border-negative/30 bg-negative/[0.07] px-4 py-3 text-[13px] text-negative">
          {error}
        </div>
      )}

      {!result && !running && (
        <Card>
          <EmptyState
            title="Ready when you are"
            description="Press RUN FULL DEMO. The backend generates a fresh task with a hidden answer, dispatches it to every registered miner, grades the responses, issues adversarial mutation probes, updates reputation and recomputes the normalised emission vector — then this page shows what changed."
            action={<Button variant="primary" onClick={run}>Run full demo</Button>} />
        </Card>
      )}

      {result && (
        <>
          <Card className="mb-4">
            <CardHeader title="Pipeline executed" subtitle="Stages reported by the backend for this exact run" />
            <ol className="divide-y divide-line/60">
              {result.stages.map((s, i) => {
                const shown = visible > i;
                return (
                  <li key={s.stage}
                    className={`flex items-center gap-3 px-5 py-3 transition-opacity duration-300 ${shown ? "opacity-100" : "opacity-25"}`}>
                    <span className="font-mono text-2xs text-ink-3">{String(i + 1).padStart(2, "0")}</span>
                    {shown
                      ? <CircleCheck size={14} className="text-positive" />
                      : <span className="h-3.5 w-3.5 rounded-full border border-line-hi" />}
                    <span className="text-[13px] text-ink-1">{s.label}</span>
                    <span className="ml-auto truncate text-right text-xs text-ink-3">{s.detail}</span>
                  </li>
                );
              })}
            </ol>
          </Card>

          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
            <Card className="rounded-none border-0">
              <Stat label="Task family" value={categoryLabel[result.task.category] ?? result.task.category}
                hint={`difficulty ${result.task.difficulty}/10 · ${result.task.generator}`} />
            </Card>
            <Card className="rounded-none border-0">
              <Stat label="Correct answers" tone="positive"
                value={`${scored.filter((r) => r.correct).length}/${scored.length}`}
                hint={`${result.task.dropped_miners.length} miners timed out`} />
            </Card>
            <Card className="rounded-none border-0">
              <Stat label="Verification confidence" tone="accent"
                value={num(result.task.consensus.verification_confidence)}
                hint={`agreement ${pct(result.task.consensus.agreement, 0)}`} />
            </Card>
            <Card className="rounded-none border-0">
              <Stat label="Probes issued" value={scored.filter((r) => r.probe).length}
                hint="semantics-preserving mutations" />
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader title="The task" subtitle={`${result.task.task_id} · ${result.task.verification_type} verification`}
                right={<Link href={`/tasks/${result.task.task_id}`}><Label>Full record →</Label></Link>} />
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap px-5 py-4 font-mono text-xs leading-relaxed text-ink-2">
                {result.task.prompt}
              </pre>
              <div className="border-t border-line px-5 py-3">
                <Label>Hidden ground truth (revealed only because this task is now closed)</Label>
                <p className="mt-1.5 font-mono text-[13px] text-mint">{result.task.ground_truth ?? "—"}</p>
                <p className="mt-1 text-xs text-ink-3">{result.task.ground_truth_explanation}</p>
              </div>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader title="Miner answers" subtitle="Independently graded" />
              <div className="max-h-[420px] divide-y divide-line/60 overflow-y-auto">
                {scored.map((r) => (
                  <div key={r.miner_uid} className="px-5 py-2.5">
                    <div className="flex items-center gap-2">
                      <Link href={`/miners/${r.miner_uid}`} className="text-[13px] text-ink-1 hover:text-accent">
                        {r.miner_name}
                      </Link>
                      {r.correct
                        ? <CircleCheck size={12} className="text-positive" />
                        : <CircleX size={12} className="text-negative" />}
                      {r.probe && (
                        <Badge tone={r.probe.consistent ? "positive" : "negative"}>
                          <Radar size={9} />{r.probe.consistent ? "held" : "flipped"}
                        </Badge>
                      )}
                      <span className="ml-auto font-mono text-xs text-ink-1">{num(r.score)}</span>
                    </div>
                    <p className="mt-1 flex items-center gap-3 font-mono text-2xs text-ink-3">
                      <span className="max-w-[130px] truncate">“{r.answer}”</span>
                      <span>conf {pct(r.confidence, 0)}</span>
                      <span>{ms(r.execution_time_ms)}</span>
                    </p>
                    <Meter value={r.score} className="mt-1.5" />
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader title="Leaderboard after this task"
                subtitle="Reputation and emission weight recomputed by the backend" />
              <Table>
                <thead>
                  <tr>
                    <Th>#</Th><Th>Miner</Th><Th align="right">Reputation</Th>
                    <Th align="right">Accuracy</Th><Th align="right">Emission</Th><Th align="right">Δ</Th>
                  </tr>
                </thead>
                <tbody>
                  {result.leaderboard.map((m) => {
                    const move = result.movements.find((x) => x.uid === m.uid);
                    return (
                      <tr key={m.uid} className="hover:bg-surface-2/60">
                        <Td className="font-mono text-ink-3">{m.rank}</Td>
                        <Td>
                          <Link href={`/miners/${m.uid}`} className="text-ink-1 hover:text-accent">{m.name}</Link>
                        </Td>
                        <Td align="right" className="font-mono">{num(m.reputation)}</Td>
                        <Td align="right">{pct(m.accuracy)}</Td>
                        <Td align="right" className="font-mono text-accent">{pct(m.emission_weight, 2)}</Td>
                        <Td align="right">
                          {!move || move.delta === 0 ? <span className="text-ink-3">—</span>
                            : move.delta > 0
                              ? <span className="inline-flex items-center gap-1 text-positive"><ArrowUp size={11} />{move.delta}</span>
                              : <span className="inline-flex items-center gap-1 text-negative"><ArrowDown size={11} />{Math.abs(move.delta)}</span>}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </Card>

            <div className="space-y-4 lg:col-span-2">
              <Card>
                <CardHeader title="Emission redistribution" subtitle="Before → after this single task" />
                {movers.length ? (
                  <div className="divide-y divide-line/60">
                    {movers.map((m) => (
                      <div key={m.uid} className="flex items-center gap-3 px-5 py-2.5">
                        <span className="text-[13px] text-ink-1">{m.name}</span>
                        <span className="ml-auto font-mono text-xs text-ink-3">
                          {pct(m.emission_before, 2)} → <span className="text-accent">{pct(m.emission_after, 2)}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="px-5 py-4 text-xs leading-relaxed text-ink-3">
                    No rank changed on this task — which is the expected outcome of a
                    smoothed mechanism. Reputation moves by at most α × (score −
                    reputation) per task, so a single result cannot reshuffle the
                    network. Run the demo a few times, or use the simulation page for
                    a longer horizon.
                  </p>
                )}
              </Card>

              <Card>
                <CardHeader title="Events from this run" subtitle="Emitted by the validator during the demo" />
                <div className="max-h-[300px] overflow-y-auto">
                  <EventFeed events={[...result.events].reverse()} limit={40} compact />
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </>
  );
}
