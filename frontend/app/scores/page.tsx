"use client";

import { Calculator, Info } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import useSWR from "swr";
import { PageHeader } from "@/components/shell";
import {
  Badge, Card, CardHeader, EmptyState, ErrorState, Label, LoadingRow, Meter,
  Select, Table, Td, Th,
} from "@/components/ui";
import { useMechanism, useMiners } from "@/hooks/use-api";
import { fetcher } from "@/lib/api";
import { num, pct } from "@/lib/format";
import type { ScoreExplanation } from "@/types";

export const dynamic = "force-dynamic";

function ScoreExplorer() {
  const params = useSearchParams();
  const { data: miners } = useMiners();
  const { data: mechanism } = useMechanism();
  const [uid, setUid] = React.useState<string>(params.get("miner") ?? "");
  const taskId = params.get("task") ?? undefined;

  React.useEffect(() => {
    if (!uid && miners?.items.length) setUid(String(miners.items[0].uid));
  }, [miners, uid]);

  const { data, error, isLoading } = useSWR<ScoreExplanation>(
    uid ? `/api/scores/${uid}${taskId ? `?task_id=${taskId}` : ""}` : null, fetcher);

  const miner = miners?.items.find((m) => String(m.uid) === uid);

  return (
    <>
      <PageHeader
        title="Score explorer"
        description="Exactly why a miner received the score it received. Every number below is recomputed from the stored evaluation — the page performs no arithmetic of its own beyond formatting."
        actions={
          <Select label="Miner" value={uid} onChange={setUid}
            options={(miners?.items ?? []).map((m) => ({
              value: String(m.uid), label: `${m.name} · ${m.profile_label}` }))} />
        }
      />

      {error ? <ErrorState error={String(error)} />
        : isLoading || !data ? <Card><LoadingRow label="Loading score breakdown" /></Card> : (
        <div className="grid items-start gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader
              title={`FINAL SCORE — ${data.miner_name}`}
              subtitle={<>task <Link href={`/tasks/${data.task_id}`} className="font-mono text-accent">{data.task_id}</Link></>}
              right={<Badge tone="accent">UID {data.miner_uid}</Badge>}
            />
            <div className="px-5 py-6">
              <p className="font-mono text-[56px] leading-none text-accent">{num(data.final_score)}</p>
              <p className="mt-2 font-mono text-2xs uppercase tracking-[0.14em] text-ink-3">
                {data.formula}
              </p>
            </div>
            <Table>
              <thead>
                <tr>
                  <Th>Component</Th><Th align="right">Value</Th><Th align="right">Weight</Th>
                  <Th align="right">Contribution</Th><Th></Th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.component}>
                    <Td className="capitalize text-ink-1">{r.component}</Td>
                    <Td align="right" className="font-mono">{num(r.value)}</Td>
                    <Td align="right" className="font-mono text-ink-3">× {pct(r.weight, 0)}</Td>
                    <Td align="right" className="font-mono text-ink-1">= {num(r.contribution)}</Td>
                    <Td className="w-32"><Meter value={r.value} /></Td>
                  </tr>
                ))}
                <tr className="bg-surface-2/50">
                  <Td className="font-medium text-ink-1">Subtotal</Td>
                  <Td /><Td />
                  <Td align="right" className="font-mono text-ink-1">{num(data.subtotal)}</Td>
                  <Td />
                </tr>
                {Object.entries(data.penalties).map(([k, v]) => (
                  <tr key={k}>
                    <Td className="text-negative">penalty · {k}</Td>
                    <Td /><Td />
                    <Td align="right" className="font-mono text-negative">−{num(v)}</Td>
                    <Td />
                  </tr>
                ))}
                <tr className="bg-accent/[0.06]">
                  <Td className="font-semibold text-accent">TOTAL</Td>
                  <Td /><Td />
                  <Td align="right" className="font-mono font-semibold text-accent">{num(data.final_score)}</Td>
                  <Td />
                </tr>
              </tbody>
            </Table>
          </Card>

          <div className="space-y-4">
            <Card>
              <CardHeader title="From score to emission" subtitle="What happens next" />
              <div className="space-y-4 px-5 py-4 text-[13px] leading-relaxed text-ink-2">
                <Step n="01" title="Temporal smoothing"
                  body={`The task score enters an exponentially weighted moving average with α = ${data.ema_alpha}. One task can move reputation by at most α × (score − reputation).`} />
                <Step n="02" title="Trust ramp"
                  body={`Below ${mechanism?.reputation?.min_tasks_for_full_trust ?? 20} scored tasks the rolling score is shrunk toward a low prior, so a small sample cannot buy a top rank.`} />
                <Step n="03" title="Eligibility"
                  body={`Miners under ${mechanism?.emission?.min_tasks ?? 10} tasks or below reputation ${mechanism?.emission?.floor_score ?? 0.25} receive zero weight.`} />
                <Step n="04" title="Normalisation"
                  body={`Surplus above the floor is raised to the power ${mechanism?.emission?.temperature ?? 2.5}, normalised to sum to 1, then capped per miner.`} />
                <div className="rounded-md border border-line bg-surface-2 px-3 py-2.5">
                  <Label>Current state</Label>
                  <div className="mt-2 flex items-baseline justify-between">
                    <span className="text-xs text-ink-3">reputation</span>
                    <span className="font-mono text-sm text-ink-1">{num(data.reputation_after)}</span>
                  </div>
                  <div className="mt-1 flex items-baseline justify-between">
                    <span className="text-xs text-ink-3">emission weight</span>
                    <span className="font-mono text-sm text-accent">{pct(data.emission_weight, 3)}</span>
                  </div>
                </div>
              </div>
            </Card>

            {miner && (
              <Card>
                <CardHeader title="Miner context" subtitle={miner.profile_label} />
                <div className="space-y-2 px-5 py-4 text-[13px]">
                  <Row label="Rank" value={`#${miner.rank}`} />
                  <Row label="Reputation" value={num(miner.reputation)} />
                  <Row label="Accuracy" value={pct(miner.accuracy)} />
                  <Row label="Scored tasks" value={String(miner.task_count)} />
                  <Row label="Flags" value={Object.keys(miner.flags).join(", ") || "none"} />
                  <Link href={`/miners/${miner.uid}`}
                    className="mt-2 inline-block text-xs text-accent hover:underline">
                    Full miner profile →
                  </Link>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}

      <Card className="mt-4">
        <CardHeader title="Weight configuration"
          subtitle="Loaded from subnet/scoring/config.py — the same object the scorer used"
          right={<Info size={13} className="text-ink-3" />} />
        <div className="flex flex-wrap gap-3 px-5 py-4">
          {Object.entries(mechanism?.weights ?? {}).map(([k, v]) => (
            <div key={k} className="rounded-md border border-line bg-surface-2 px-3 py-2">
              <Label>{k}</Label>
              <p className="mt-1 font-mono text-sm text-accent">{pct(Number(v), 0)}</p>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

export default function ScoresPage() {
  return (
    <React.Suspense fallback={<Card><LoadingRow /></Card>}>
      <ScoreExplorer />
    </React.Suspense>
  );
}

function Step({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div className="flex gap-3">
      <span className="font-mono text-2xs text-ink-3">{n}</span>
      <div>
        <p className="text-[13px] font-medium text-ink-1">{title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-ink-3">{body}</p>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-xs text-ink-3">{label}</span>
      <span className="truncate font-mono text-xs text-ink-1">{value}</span>
    </div>
  );
}
