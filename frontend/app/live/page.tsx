"use client";

import { CircleCheck, CircleX, Play, Radar, Wifi, WifiOff } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { useSWRConfig } from "swr";
import { PageHeader } from "@/components/shell";
import {
  Badge, Button, Card, CardHeader, EmptyState, Label, LoadingRow, Meter, Stat,
} from "@/components/ui";
import { EventFeed } from "@/components/event-feed";
import { useEventStream } from "@/hooks/use-event-stream";
import { useStats, useTasks } from "@/hooks/use-api";
import { api } from "@/lib/api";
import { categoryLabel, ms, num, pct, timeAgo } from "@/lib/format";
import type { TaskDetail } from "@/types";

const STAGES = ["GENERATED", "DISPATCHED", "RESPONSES RECEIVED", "VERIFIED", "SCORED"];

export default function LiveVerificationPage() {
  const { connected, events } = useEventStream(true, 150);
  const { data: stats } = useStats(6000);
  const { data: recent } = useTasks("limit=6");
  const { mutate } = useSWRConfig();
  const [task, setTask] = React.useState<TaskDetail | null>(null);
  const [stage, setStage] = React.useState(-1);
  const [running, setRunning] = React.useState(false);

  const run = async () => {
    setRunning(true);
    setTask(null);
    setStage(0);
    try {
      // animate the pipeline while the backend actually executes it
      const timers = STAGES.map((_, i) =>
        setTimeout(() => setStage(i), i * 260));
      const result = await api.createTask({});
      timers.forEach(clearTimeout);
      setStage(STAGES.length - 1);
      setTask(result);
      await mutate((key) => typeof key === "string" && key.startsWith("/api/"));
    } finally {
      setRunning(false);
    }
  };

  const shown = task;
  const scored = shown?.responses.filter((r) => !r.rejected) ?? [];

  return (
    <>
      <PageHeader
        title="Live verification"
        description="A real task executed through the full validator pipeline, plus the raw event stream emitted by every validator in this process."
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={connected ? "positive" : "warning"}>
              {connected ? <Wifi size={10} /> : <WifiOff size={10} />}
              {connected ? "SSE connected" : "polling fallback"}
            </Badge>
            <Button variant="primary" onClick={run} disabled={running}>
              <Play size={13} /> {running ? "Verifying…" : "Verify a new task"}
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
        <Card className="rounded-none border-0">
          <Stat label="Tasks verified" value={stats?.tasks_verified ?? "—"} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Events emitted" value={stats?.events ?? "—"} tone="accent" />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Probes issued" value={stats?.robustness_probes ?? "—"}
            hint={`${pct(stats?.robustness_hold_rate)} held`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Rejected responses" value={stats?.rejected_responses ?? "—"}
            tone="warning" hint="replay / nonce / rate limit" />
        </Card>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          <Card>
            <CardHeader
              title={shown ? `TASK ${shown.task_id}` : "Verification pipeline"}
              subtitle={shown
                ? `${categoryLabel[shown.category]} · difficulty ${shown.difficulty}/10 · ${shown.verification_type}`
                : "Press “Verify a new task” to generate, dispatch, grade and score a task now."}
              right={shown ? <Badge tone="positive">{shown.status}</Badge> : undefined}
            />
            <div className="flex flex-wrap items-center gap-2 px-5 py-4">
              {STAGES.map((s, i) => {
                const done = stage >= i;
                return (
                  <React.Fragment key={s}>
                    <div className={`flex items-center gap-2 rounded-sm border px-2.5 py-1.5 transition-colors ${
                      done ? "border-positive/25 bg-positive/[0.07]" : "border-line bg-surface-2"}`}>
                      {done
                        ? <CircleCheck size={12} className="text-positive" />
                        : <span className="h-2.5 w-2.5 rounded-full border border-line-hi" />}
                      <span className={`font-mono text-2xs uppercase tracking-[0.12em] ${
                        done ? "text-positive" : "text-ink-3"}`}>{s}</span>
                    </div>
                    {i < STAGES.length - 1 && <span className="text-line-hi">→</span>}
                  </React.Fragment>
                );
              })}
            </div>

            {shown ? (
              <>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap border-t border-line px-5 py-4 font-mono text-xs leading-relaxed text-ink-2">
                  {shown.prompt}
                </pre>
                <div className="divide-y divide-line/60 border-t border-line">
                  {scored.map((r) => (
                    <div key={r.miner_uid} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2.5">
                      <Link href={`/miners/${r.miner_uid}`}
                        className="w-32 truncate text-[13px] text-ink-1 hover:text-accent">
                        {r.miner_name}
                      </Link>
                      {r.correct
                        ? <span className="flex items-center gap-1.5 text-xs text-positive"><CircleCheck size={12} />Correct</span>
                        : <span className="flex items-center gap-1.5 text-xs text-negative"><CircleX size={12} />Incorrect</span>}
                      <span className="font-mono text-xs text-ink-3">conf {pct(r.confidence, 0)}</span>
                      <span className="font-mono text-xs text-ink-3">{ms(r.execution_time_ms)}</span>
                      <span className="max-w-[180px] truncate font-mono text-xs text-ink-2">{r.answer}</span>
                      {r.probe && (
                        <Badge tone={r.probe.consistent ? "positive" : "negative"}>
                          <Radar size={10} />{r.probe.consistent ? "probe held" : "probe flipped"}
                        </Badge>
                      )}
                      <span className="ml-auto flex items-center gap-2">
                        <Meter value={r.score} className="w-14" />
                        <span className="w-10 text-right font-mono text-xs text-ink-1">{num(r.score)}</span>
                      </span>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-6 border-t border-line px-5 py-3.5">
                  <div>
                    <Label>Consensus</Label>
                    <p className="font-mono text-sm text-ink-1">{pct(shown.consensus.agreement)}</p>
                  </div>
                  <div>
                    <Label>Verification confidence</Label>
                    <p className="font-mono text-sm text-accent">{num(shown.consensus.verification_confidence)}</p>
                  </div>
                  <div>
                    <Label>Result</Label>
                    <p className="font-mono text-sm text-positive">
                      {shown.consensus.verification_confidence >= 0.5 ? "VERIFIED" : "DISPUTED"}
                    </p>
                  </div>
                  <Link href={`/tasks/${shown.task_id}`} className="ml-auto text-xs text-accent hover:underline">
                    Full task record →
                  </Link>
                </div>
              </>
            ) : running ? <LoadingRow label="Running the pipeline" /> : (
              <EmptyState title="No task running"
                description="This view never fabricates activity. Trigger a task to see the pipeline execute, or watch the event stream for tasks issued by other validators."
                action={<Button size="sm" variant="primary" onClick={run}>Verify a task</Button>} />
            )}
          </Card>

          <Card>
            <CardHeader title="Recently verified" subtitle="Last six closed tasks" />
            <div className="divide-y divide-line/60">
              {(recent?.items ?? []).map((t) => (
                <Link key={t.task_id} href={`/tasks/${t.task_id}`}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2.5 transition-colors hover:bg-surface-2/60">
                  <span className="font-mono text-xs text-ink-3">{t.task_id}</span>
                  <span className="text-xs text-ink-2">{categoryLabel[t.category]}</span>
                  <Badge>{t.difficulty}/10</Badge>
                  <span className="text-xs text-ink-3">
                    {t.correct_responses}/{t.responses} correct
                  </span>
                  <span className="ml-auto font-mono text-xs text-accent">
                    {pct(t.consensus?.verification_confidence, 0)}
                  </span>
                  <span className="w-16 text-right text-2xs text-ink-3">{timeAgo(t.created_at)}</span>
                </Link>
              ))}
            </div>
          </Card>
        </div>

        <Card className="lg:col-span-2">
          <CardHeader title="Validator event stream"
            subtitle="Server-sent events straight from the event bus"
            right={<Label>{events.length} buffered</Label>} />
          <div className="max-h-[760px] overflow-y-auto">
            <EventFeed limit={80} />
          </div>
        </Card>
      </div>
    </>
  );
}
