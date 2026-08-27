"use client";

import {
  ArrowLeft, CircleCheck, CircleX, Eye, EyeOff, Lock, Radar, TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";
import { PageHeader } from "@/components/shell";
import {
  Badge, Card, CardHeader, EmptyState, ErrorState, Label, LoadingRow, Meter,
  Stat, Table, Td, Th,
} from "@/components/ui";
import { useTask } from "@/hooks/use-api";
import { categoryLabel, ms, num, pct, timeAgo } from "@/lib/format";

const STAGES = ["GENERATED", "DISPATCHED", "RESPONSES RECEIVED", "VERIFIED", "SCORED"];

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: t, error, isLoading } = useTask(params.id);
  const [showEvidence, setShowEvidence] = React.useState<number | null>(null);

  if (error) return <ErrorState error={String(error)} />;
  if (isLoading || !t) return <Card><LoadingRow label="Loading task" /></Card>;

  const scored = t.responses.filter((r) => !r.rejected);
  const correct = scored.filter((r) => r.correct).length;

  return (
    <>
      <Link href="/tasks" className="mb-4 inline-flex items-center gap-1.5 text-xs text-ink-3 hover:text-accent">
        <ArrowLeft size={12} /> Task explorer
      </Link>

      <PageHeader
        title={categoryLabel[t.category] ?? t.category}
        description={`${t.generator} · difficulty ${t.difficulty}/10 · ${t.verification_type} verification · issued by ${t.validator_name}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Badge tone="accent">{t.task_id}</Badge>
            <Badge tone={t.kind === "adversarial" ? "warning" : "neutral"}>{t.kind}</Badge>
            <Badge tone="positive">{t.status}</Badge>
          </div>
        }
      />

      {/* pipeline */}
      <Card className="mb-5">
        <div className="flex flex-wrap items-center gap-2 px-5 py-4">
          {STAGES.map((s, i) => (
            <React.Fragment key={s}>
              <div className="flex items-center gap-2 rounded-sm border border-positive/25 bg-positive/[0.07] px-2.5 py-1.5">
                <CircleCheck size={12} className="text-positive" />
                <span className="font-mono text-2xs uppercase tracking-[0.12em] text-positive">{s}</span>
              </div>
              {i < STAGES.length - 1 && <span className="text-line-hi">→</span>}
            </React.Fragment>
          ))}
          <span className="ml-auto font-mono text-2xs text-ink-3">
            wall clock {ms(t.duration_ms)} · {timeAgo(t.created_at)}
          </span>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
        <Card className="rounded-none border-0">
          <Stat label="Responses" value={`${scored.length}`}
            hint={`${t.dropped_miners.length} timeouts · ${t.responses.length - scored.length} rejected`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Correct" tone="positive" value={`${correct}/${scored.length}`}
            hint={pct(scored.length ? correct / scored.length : 0, 0) + " of graded answers"} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Consensus agreement" value={pct(t.consensus?.agreement)}
            hint="reputation-weighted answer agreement" />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Verification confidence" tone="accent"
            value={num(t.consensus?.verification_confidence)}
            hint="0.5 × agreement + 0.5 × verified-correct share" />
        </Card>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Task prompt" subtitle="Exactly what every miner received" />
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap px-5 py-4 font-mono text-xs leading-relaxed text-ink-2">
            {t.prompt}
          </pre>
        </Card>

        <Card>
          <CardHeader title="Ground truth status" subtitle="Hidden benchmark protection" />
          <div className="space-y-4 px-5 py-4 text-[13px] leading-relaxed text-ink-2">
            <div className="flex items-start gap-2.5">
              <Lock size={14} className="mt-0.5 shrink-0 text-mint" />
              <p>
                The hidden answer is <span className="text-ink-1">held server-side</span> and is
                not part of this response. Only an authenticated admin request can
                reveal it, and only for a closed task.
              </p>
            </div>
            <div>
              <Label>HMAC commitment</Label>
              <p className="mt-1 break-all font-mono text-2xs text-ink-3">{t.commitment}</p>
              <p className="mt-1.5 text-xs text-ink-3">
                Computed over (task id, nonce, hidden answer) before dispatch, so the
                validator cannot adapt the answer after seeing responses.
              </p>
            </div>
            {t.parent_task_id && (
              <div>
                <Label>Mutation parent</Label>
                <Link href={`/tasks/${t.parent_task_id}`}
                  className="mt-1 block font-mono text-xs text-accent">{t.parent_task_id}</Link>
              </div>
            )}
            <div>
              <Label>Verification type</Label>
              <p className="mt-1 font-mono text-xs text-ink-1">{t.verification_type}</p>
            </div>
          </div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader title="Miner responses"
          subtitle="Independently graded. Score = Σ(component × weight) × (1 − penalties)."
          right={<Label>{t.responses.length} submissions</Label>} />
        {t.responses.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Miner</Th><Th>Answer</Th><Th align="center">Verdict</Th>
                <Th align="right">Confidence</Th><Th align="right">Latency</Th>
                <Th align="right">Acc</Th><Th align="right">Evid</Th><Th align="right">Rob</Th>
                <Th align="right">Cal</Th><Th align="right">Lat</Th>
                <Th align="right">Score</Th><Th align="center">Probe</Th><Th></Th>
              </tr>
            </thead>
            <tbody>
              {t.responses.map((r) => (
                <React.Fragment key={r.miner_uid}>
                  <tr className="transition-colors hover:bg-surface-2/60">
                    <Td>
                      <Link href={`/miners/${r.miner_uid}`} className="text-ink-1 hover:text-accent">
                        {r.miner_name}
                      </Link>
                      {r.flags.length > 0 && (
                        <span className="ml-1.5 align-middle">
                          <TriangleAlert size={11} className="inline text-warning" />
                        </span>
                      )}
                    </Td>
                    <Td>
                      <span className="line-clamp-1 max-w-[220px] font-mono text-xs text-ink-2">
                        {r.rejected ? <em className="text-negative">rejected: {r.rejection_reason}</em> : r.answer}
                      </span>
                    </Td>
                    <Td align="center">
                      {r.rejected ? <span className="text-ink-3">—</span>
                        : r.correct ? <CircleCheck size={14} className="mx-auto text-positive" />
                          : <CircleX size={14} className="mx-auto text-negative" />}
                    </Td>
                    <Td align="right">{pct(r.confidence, 0)}</Td>
                    <Td align="right">{ms(r.execution_time_ms)}</Td>
                    <Td align="right">{num(r.breakdown?.accuracy ?? 0, 2)}</Td>
                    <Td align="right">{num(r.breakdown?.evidence ?? 0, 2)}</Td>
                    <Td align="right">{num(r.breakdown?.robustness ?? 0, 2)}</Td>
                    <Td align="right">{num(r.breakdown?.calibration ?? 0, 2)}</Td>
                    <Td align="right">{num(r.breakdown?.latency ?? 0, 2)}</Td>
                    <Td align="right">
                      <div className="flex items-center justify-end gap-2">
                        <span className="font-mono text-ink-1">{num(r.score)}</span>
                        <Meter value={r.score} className="w-10" />
                      </div>
                    </Td>
                    <Td align="center">
                      {r.probe ? (
                        <Badge tone={r.probe.consistent ? "positive" : "negative"}>
                          <Radar size={10} />{r.probe.consistent ? "held" : "flipped"}
                        </Badge>
                      ) : <span className="text-ink-3">—</span>}
                    </Td>
                    <Td align="right">
                      <button onClick={() => setShowEvidence(showEvidence === r.miner_uid ? null : r.miner_uid)}
                        className="text-ink-3 hover:text-accent">
                        {showEvidence === r.miner_uid ? <EyeOff size={13} /> : <Eye size={13} />}
                      </button>
                    </Td>
                  </tr>
                  {showEvidence === r.miner_uid && (
                    <tr>
                      <td colSpan={13} className="border-b border-line bg-surface-2/40 px-5 py-4">
                        <div className="grid gap-5 md:grid-cols-3">
                          <div className="md:col-span-2">
                            <Label>Submitted evidence</Label>
                            {r.evidence.length ? (
                              <ul className="mt-2 space-y-1.5">
                                {r.evidence.map((e, i) => (
                                  <li key={i} className="font-mono text-xs leading-relaxed text-ink-2">
                                    <span className="text-ink-3">{String(i + 1).padStart(2, "0")}</span> {e}
                                  </li>
                                ))}
                              </ul>
                            ) : <p className="mt-2 text-xs text-ink-3">No evidence supplied.</p>}
                            <p className="mt-3 font-mono text-2xs text-ink-3">
                              full answer: {r.answer || "—"}
                            </p>
                          </div>
                          <div>
                            <Label>Penalties & flags</Label>
                            {Object.keys(r.penalties).length === 0 && r.flags.length === 0 ? (
                              <p className="mt-2 text-xs text-ink-3">None.</p>
                            ) : (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {r.flags.map((f) => <Badge key={f} tone="warning">{f}</Badge>)}
                                {Object.entries(r.penalties).map(([k, v]) => (
                                  <Badge key={k} tone="negative">{k} −{num(v, 2)}</Badge>
                                ))}
                              </div>
                            )}
                            <div className="mt-3">
                              <Label>Backend</Label>
                              <p className="mt-1 font-mono text-2xs text-ink-3">
                                {JSON.stringify(r.model_metadata)}
                              </p>
                            </div>
                            {r.probe && (
                              <div className="mt-3">
                                <Label>Mutation probe</Label>
                                <p className="mt-1 text-xs text-ink-2">
                                  Answer under mutation: <span className="font-mono">{r.probe.answer ?? "—"}</span>
                                </p>
                                <pre className="mt-1.5 max-h-32 overflow-auto whitespace-pre-wrap rounded-sm border border-line bg-bg px-2.5 py-2 font-mono text-2xs text-ink-3">
                                  {r.probe.prompt_excerpt}
                                </pre>
                              </div>
                            )}
                            <Link href={`/scores?miner=${r.miner_uid}&task=${t.task_id}`}
                              className="mt-3 inline-block text-xs text-accent hover:underline">
                              Open score breakdown →
                            </Link>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </Table>
        ) : <EmptyState title="No responses" description="No miner answered this task before the deadline." />}
      </Card>
    </>
  );
}
