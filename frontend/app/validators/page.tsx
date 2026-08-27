"use client";

import { Radar, ShieldCheck, Target } from "lucide-react";
import { PageHeader } from "@/components/shell";
import {
  Badge, Card, CardHeader, ErrorState, Label, LoadingRow, Meter, Table, Td, Th,
} from "@/components/ui";
import { useHealth, useValidators } from "@/hooks/use-api";
import { num, pct, timeAgo } from "@/lib/format";

export default function ValidatorsPage() {
  const { data, error, isLoading } = useValidators();
  const { data: health } = useHealth();

  if (error) return <ErrorState error={String(error)} />;

  const statusOf = (uid: number) =>
    health?.validators.find((v) => v.uid === uid)?.status ?? "unknown";

  return (
    <>
      <PageHeader
        title="Validators"
        description="Each validator runs its own task engine, anti-gaming guard and scoring engine. Strategies differ in coverage, probe aggressiveness and category weighting, so a miner cannot optimise for a single evaluator."
      />

      {isLoading ? <Card><LoadingRow /></Card> : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(data ?? []).map((v) => (
              <Card key={v.uid} className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-ink-1">{v.name}</h3>
                    <p className="mt-0.5 font-mono text-2xs uppercase tracking-widest text-ink-3">
                      {v.strategy_label}
                    </p>
                  </div>
                  <Badge tone={statusOf(v.uid) === "healthy" ? "positive" : "warning"}>
                    <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-current" />
                    {statusOf(v.uid)}
                  </Badge>
                </div>
                <p className="mt-3 text-[13px] leading-relaxed text-ink-2">{v.description}</p>

                <div className="mt-4 space-y-2.5">
                  <MetricRow icon={Target} label="Miner coverage per task"
                    value={pct(v.sample_fraction, 0)} meter={v.sample_fraction} />
                  <MetricRow icon={Radar} label="Robustness probe rate"
                    value={pct(v.probe_rate, 0)} meter={v.probe_rate} />
                  <MetricRow icon={ShieldCheck} label="Difficulty policy"
                    value={v.adaptive ? "adaptive" : "fixed"} />
                </div>

                <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-md border border-line bg-line text-center">
                  {[["Issued", v.tasks_issued], ["Probes", v.probes_issued],
                    ["Rejected", v.rejections]].map(([l, n]) => (
                    <div key={String(l)} className="bg-surface-2 px-2 py-2.5">
                      <p className="font-mono text-sm text-ink-1">{n as number}</p>
                      <p className="mt-0.5 font-mono text-2xs uppercase tracking-widest text-ink-3">{l}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-2xs text-ink-3">
                  Last active {v.last_active ? timeAgo(v.last_active) : "—"} ·
                  guard tracking {v.guard.tracked_tasks} tasks
                </p>
              </Card>
            ))}
          </div>

          <Card className="mt-5">
            <CardHeader title="Validator activity" subtitle="Independent evaluation volume"
              right={<Label>{data?.length ?? 0} validators</Label>} />
            <Table>
              <thead>
                <tr>
                  <Th>Validator</Th><Th>Strategy</Th><Th align="right">Tasks issued</Th>
                  <Th align="right">Tasks scored</Th><Th align="right">Probes</Th>
                  <Th align="right">Rejections</Th><Th align="right">Submissions seen</Th>
                </tr>
              </thead>
              <tbody>
                {(data ?? []).map((v) => (
                  <tr key={v.uid} className="hover:bg-surface-2/60">
                    <Td className="text-ink-1">{v.name}</Td>
                    <Td><Badge>{v.strategy}</Badge></Td>
                    <Td align="right">{v.tasks_issued}</Td>
                    <Td align="right">{v.tasks_scored}</Td>
                    <Td align="right">{v.probes_issued}</Td>
                    <Td align="right" className={v.rejections ? "text-warning" : ""}>{v.rejections}</Td>
                    <Td align="right">{v.guard.recorded_submissions}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </>
      )}
    </>
  );
}

function MetricRow({ icon: Icon, label, value, meter }: {
  icon: any; label: string; value: string; meter?: number;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <Icon size={13} className="text-ink-3" />
      <span className="text-xs text-ink-2">{label}</span>
      <span className="ml-auto font-mono text-xs text-ink-1">{value}</span>
      {meter !== undefined && <Meter value={meter} className="w-12" />}
    </div>
  );
}
