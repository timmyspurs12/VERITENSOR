"use client";

import { ArrowLeft, CircleCheck, CircleX, Radar, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/shell";
import {
  Badge, Card, CardHeader, EmptyState, ErrorState, Label, LoadingRow, Meter,
  Stat, Table, Td, Th,
} from "@/components/ui";
import { BarSeries, ComponentRadar, TrendChart } from "@/components/charts";
import { useMiner } from "@/hooks/use-api";
import { categoryColor, categoryLabel, ms, num, pct, timeAgo } from "@/lib/format";

export default function MinerProfilePage() {
  const params = useParams<{ uid: string }>();
  const uid = Number(params.uid);
  const { data: m, error, isLoading } = useMiner(Number.isFinite(uid) ? uid : null);

  if (error) return <ErrorState error={String(error)} />;
  if (isLoading || !m) return <Card><LoadingRow label="Loading miner profile" /></Card>;

  const history = m.history.map((h, i) => ({
    i: i + 1,
    score: h.score,
    reputation: h.rolling_score,
    accuracy: h.accuracy,
    emission: h.emission_weight,
  }));

  const categories = Object.entries(m.categories).map(([k, v]) => ({
    name: categoryLabel[k] ?? k, accuracy: v.accuracy, tasks: v.tasks,
    score: v.mean_score, fill: categoryColor[k] ?? "#7DD6FA",
  }));

  const failures = Object.entries(m.failure_analysis).map(([k, v]) => ({
    name: categoryLabel[k] ?? k, failures: v, fill: "#F27E88",
  }));

  const radar = Object.entries(m.components).map(([k, v]) => ({
    component: k.slice(0, 5), value: v ?? 0,
  }));

  const probesHeld = m.probe_outcomes.filter(Boolean).length;

  return (
    <>
      <Link href="/miners" className="mb-4 inline-flex items-center gap-1.5 text-xs text-ink-3 hover:text-accent">
        <ArrowLeft size={12} /> Leaderboard
      </Link>

      <PageHeader
        title={m.name}
        description={m.profile_description}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="accent">UID {m.uid}</Badge>
            <Badge>{m.profile_label}</Badge>
            <Badge tone="warning">synthetic</Badge>
            <Link href={`/scores?miner=${m.uid}`}>
              <Badge tone="mint">Explain score →</Badge>
            </Link>
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-5">
        <Card className="rounded-none border-0">
          <Stat label="Reputation" tone="accent" value={num(m.reputation)}
            hint={`rolling ${num(m.rolling_score)} · lifetime ${num(m.lifetime_score)}`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Accuracy" value={pct(m.accuracy)} hint={`${m.task_count} scored tasks`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Mean latency" value={ms(m.mean_latency_ms)}
            hint={`latency component ${num(m.components.latency ?? 0, 2)}`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Robustness probes" value={`${probesHeld}/${m.probe_outcomes.length}`}
            tone={probesHeld === m.probe_outcomes.length ? "positive" : "warning"}
            hint="mutation probes where the verdict held" />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Emission weight" tone="positive" value={pct(m.emission_weight, 2)}
            hint={`specialisation: ${m.specialisation ?? "—"}`} />
        </Card>
      </div>

      <div className="mt-5 grid items-start gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Reputation timeline"
            subtitle="Per-task score against the exponentially weighted rolling reputation"
            right={<Label>{history.length} tasks</Label>} />
          <div className="p-4">
            {history.length ? (
              <TrendChart data={history} xKey="i" height={240} domain={[0, 1]}
                format={(v) => v.toFixed(2)}
                series={[
                  { key: "score", label: "Task score", color: "#3EA8D6" },
                  { key: "reputation", label: "Rolling reputation", color: "#7DD6FA" },
                  { key: "accuracy", label: "Cumulative accuracy", color: "#A8F0C6" },
                ]} />
            ) : <EmptyState title="No history" description="This miner has not been scored yet." />}
          </div>
        </Card>

        <Card>
          <CardHeader title="Score components" subtitle="Most recent scored task" />
          <div className="p-4">
            <ComponentRadar values={radar} height={200} />
            <div className="mt-3 space-y-2">
              {Object.entries(m.components).map(([k, v]) => (
                <div key={k} className="flex items-center gap-3">
                  <span className="w-20 font-mono text-2xs uppercase tracking-wider text-ink-3">{k}</span>
                  <Meter value={v ?? 0} />
                  <span className="w-10 text-right font-mono text-xs text-ink-1">{num(v ?? 0, 2)}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Emission history" subtitle="Weight after each recomputation" />
          <div className="p-4">
            {m.emission_history.length ? (
              <TrendChart height={200}
                data={m.emission_history.map((v, i) => ({ i: i + 1, weight: v }))}
                xKey="i" format={(v) => `${(v * 100).toFixed(1)}%`}
                series={[{ key: "weight", label: "Emission weight", color: "#A8F0C6" }]} />
            ) : <EmptyState title="No emissions yet" description="A miner needs a minimum number of scored tasks before it becomes emission-eligible." />}
          </div>
        </Card>

        <Card>
          <CardHeader title="Task family performance" subtitle="Accuracy per verifiable family" />
          <div className="p-4">
            {categories.length ? (
              <BarSeries data={categories} xKey="name" yKey="accuracy" colorKey="fill"
                height={200} format={(v) => `${(v * 100).toFixed(0)}%`} />
            ) : <LoadingRow />}
          </div>
        </Card>

        <Card>
          <CardHeader title="Failure analysis" subtitle="Incorrect answers by family" />
          <div className="p-4">
            {failures.length ? (
              <BarSeries data={failures} xKey="name" yKey="failures" colorKey="fill" height={200} />
            ) : (
              <EmptyState title="No failures recorded" description="Every graded response from this miner has been correct so far." />
            )}
          </div>
        </Card>
      </div>

      {Object.keys(m.flags).length > 0 && (
        <Card className="mt-4 border-warning/25">
          <CardHeader title="Anti-gaming flags"
            subtitle="Raised by the validator guard. Flags with a configured penalty reduce the task score directly." />
          <div className="flex flex-wrap gap-2 p-5">
            {Object.entries(m.flags).map(([flag, count]) => (
              <Badge key={flag} tone="warning">
                <TriangleAlert size={10} /> {flag} × {count}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      <Card className="mt-4">
        <CardHeader title="Recent verification tasks"
          subtitle="Latest graded responses, including any adversarial mutation probe" />
        {m.recent_tasks.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Task</Th><Th>Family</Th><Th align="right">Diff</Th>
                <Th align="center">Verdict</Th><Th align="right">Confidence</Th>
                <Th align="right">Latency</Th><Th align="right">Score</Th>
                <Th align="center">Probe</Th><Th align="right">When</Th>
              </tr>
            </thead>
            <tbody>
              {m.recent_tasks.map((t) => (
                <tr key={t.task_id} className="transition-colors hover:bg-surface-2/60">
                  <Td>
                    <Link href={`/tasks/${t.task_id}`} className="font-mono text-xs text-ink-2 hover:text-accent">
                      {t.task_id}
                    </Link>
                  </Td>
                  <Td><span className="text-xs">{categoryLabel[t.category]}</span></Td>
                  <Td align="right">{t.difficulty}/10</Td>
                  <Td align="center">
                    {t.correct
                      ? <CircleCheck size={14} className="mx-auto text-positive" />
                      : <CircleX size={14} className="mx-auto text-negative" />}
                  </Td>
                  <Td align="right">{pct(t.confidence, 0)}</Td>
                  <Td align="right">{ms(t.latency_ms)}</Td>
                  <Td align="right" className="font-mono text-ink-1">{num(t.score)}</Td>
                  <Td align="center">
                    {t.probe ? (
                      <Badge tone={t.probe.consistent ? "positive" : "negative"}>
                        <Radar size={10} />{t.probe.consistent ? "held" : "flipped"}
                      </Badge>
                    ) : <span className="text-ink-3">—</span>}
                  </Td>
                  <Td align="right"><span className="text-xs text-ink-3">{timeAgo(t.created_at)}</span></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : <EmptyState title="No graded tasks" description="This miner has not answered a task yet." />}
      </Card>
    </>
  );
}
