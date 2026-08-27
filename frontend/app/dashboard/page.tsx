"use client";

import { Activity, CircleAlert, CircleCheck, Clock, Cpu, Server, Zap } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/shell";
import {
  Badge, Card, CardHeader, EmptyState, ErrorState, Label, LoadingRow, Meter,
  Stat, Table, Td, Th,
} from "@/components/ui";
import { BarSeries, TrendChart } from "@/components/charts";
import { EventFeed } from "@/components/event-feed";
import { ChainStatusPanel } from "@/components/chain-status";
import { useEmissions, useEpochs, useHealth, useMiners, useStats } from "@/hooks/use-api";
import { categoryColor, categoryLabel, compact, ms, num, pct } from "@/lib/format";

export default function DashboardPage() {
  const { data: stats, error, isLoading } = useStats();
  const { data: epochs } = useEpochs(30);
  const { data: health } = useHealth();
  const { data: miners } = useMiners();
  const { data: emissions } = useEmissions();

  if (error) return <ErrorState error={String(error)} />;

  const epochSeries = (epochs ?? []).map((e) => ({
    epoch: `E${e.epoch}`,
    accuracy: e.network_accuracy,
    score: e.network_score,
    latency: e.mean_latency_ms,
    gini: e.emission_gini,
  }));

  const categories = (stats?.categories ?? []).map((c) => ({
    name: categoryLabel[c.category] ?? c.category,
    accuracy: c.accuracy,
    tasks: c.tasks,
    fill: categoryColor[c.category],
  }));

  const top = (miners?.items ?? []).slice(0, 8);

  return (
    <>
      <PageHeader
        title={`Subnet ${stats?.netuid ?? ""} — network overview`}
        description="Every figure below is computed by the validator pipeline from real task executions in this process. Nothing on this page is hardcoded."
        actions={
          <Badge tone={health?.subnet_status === "operational" ? "positive" : "warning"}>
            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-current" />
            {health?.subnet_status ?? "…"}
          </Badge>
        }
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
        <Card className="rounded-none border-0">
          <Stat label="Active miners" value={stats?.active_miners ?? "—"} loading={isLoading}
            hint={`${stats?.emission_eligible ?? 0} emission-eligible`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Active validators" value={stats?.active_validators ?? "—"} loading={isLoading}
            hint={`${health?.validators.filter((v) => v.status === "healthy").length ?? 0} healthy`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Tasks verified" value={compact(stats?.tasks_verified ?? 0)} loading={isLoading}
            hint={`${compact(stats?.responses_evaluated ?? 0)} responses graded`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Network accuracy" tone="accent" value={pct(stats?.network_accuracy)}
            loading={isLoading} hint={`mean task score ${num(stats?.mean_task_score)}`} />
        </Card>
      </div>

      <div className="mt-px grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
        <Card className="rounded-none border-0">
          <Stat label="Verification latency" value={ms(stats?.mean_latency_ms)}
            hint={`p95 ${ms(stats?.p95_latency_ms)}`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Robustness hold rate" tone="positive" value={pct(stats?.robustness_hold_rate)}
            hint={`${compact(stats?.robustness_probes ?? 0)} mutation probes issued`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Emission concentration" value={num(stats?.emission_gini, 3)}
            hint="Gini of the current weight vector" />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Task throughput" value={`${compact(stats?.throughput_per_min ?? 0)}/min`}
            tone="warning"
            hint={stats?.throughput_is_simulated ? "in-process simulation pace" : "on-chain pace"} />
        </Card>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Network accuracy and score by epoch"
            subtitle="An epoch closes after a fixed number of verified tasks; weights are recomputed at each close."
            right={<Label>{epochSeries.length} epochs</Label>} />
          {epochSeries.length ? (
            <div className="p-4">
              <TrendChart data={epochSeries} xKey="epoch" height={230}
                format={(v) => `${(v * 100).toFixed(0)}%`} domain={[0, 1]}
                series={[
                  { key: "accuracy", label: "Accuracy", color: "#7DD6FA" },
                  { key: "score", label: "Mean reputation", color: "#A8F0C6" },
                ]} />
            </div>
          ) : <LoadingRow />}
        </Card>

        <Card>
          <CardHeader title="Network health" subtitle="Validator liveness and miner standing" />
          <div className="space-y-3 p-5">
            <HealthRow icon={Server} label="Validators"
              value={`${health?.validators.filter((v) => v.status === "healthy").length ?? 0}/${health?.validators.length ?? 0} healthy`}
              tone="positive" />
            <HealthRow icon={Cpu} label="Miners"
              value={`${health?.miner_health.healthy ?? 0} healthy · ${health?.miner_health.underperforming ?? 0} below floor`}
              tone={health?.miner_health.underperforming ? "warning" : "positive"} />
            <HealthRow icon={Activity} label="Task queue"
              value={`${health?.task_queue_depth ?? 0} open`} tone="neutral" />
            <HealthRow icon={Clock} label="Verification latency"
              value={ms(health?.verification_latency_ms)} tone="neutral" />
            <HealthRow icon={CircleAlert} label="Rejected responses"
              value={`${stats?.rejected_responses ?? 0} (replay / rate / schema)`}
              tone={stats?.rejected_responses ? "warning" : "positive"} />
            <HealthRow icon={Zap} label="Flagged miners"
              value={`${stats?.flagged_miners ?? 0} with anti-gaming flags`}
              tone={stats?.flagged_miners ? "warning" : "positive"} />
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Accuracy by task family"
            subtitle="Difficulty adapts per validator, so families are not directly comparable." />
          <div className="p-4">
            {categories.length ? (
              <BarSeries data={categories} xKey="name" yKey="accuracy" colorKey="fill"
                height={220} format={(v) => `${(v * 100).toFixed(0)}%`} />
            ) : <LoadingRow />}
          </div>
        </Card>

        <Card>
          <CardHeader title="Mean latency by epoch" subtitle="Miner-reported execution time" />
          <div className="p-4">
            {epochSeries.length ? (
              <TrendChart data={epochSeries} xKey="epoch" height={220}
                format={(v) => `${(v / 1000).toFixed(1)}s`}
                series={[{ key: "latency", label: "Mean latency", color: "#EFC468" }]} />
            ) : <LoadingRow />}
          </div>
        </Card>

        <Card>
          <CardHeader title="Current emission distribution"
            subtitle={`Total weight ${num(emissions?.total_weight, 6)} · ${emissions?.eligible ?? 0} eligible`}
            right={<Link href="/emissions"><Label>Detail →</Label></Link>} />
          <div className="p-4">
            {emissions?.items.length ? (
              <BarSeries height={220}
                data={emissions.items.slice(0, 10).map((i) => ({
                  name: i.name.split("-")[0], weight: i.emission_weight,
                  fill: i.eligible ? "#7DD6FA" : "#2A323D",
                }))}
                xKey="name" yKey="weight" colorKey="fill"
                format={(v) => `${(v * 100).toFixed(1)}%`} />
            ) : <LoadingRow />}
          </div>
        </Card>
      </div>

      <div className="mt-4">
        <ChainStatusPanel />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader title="Top performing miners"
            subtitle="Ranked by trust-shrunk rolling reputation"
            right={<Link href="/miners"><Label>Full leaderboard →</Label></Link>} />
          {top.length ? (
            <Table>
              <thead>
                <tr>
                  <Th>#</Th><Th>Miner</Th><Th align="right">Reputation</Th>
                  <Th align="right">Accuracy</Th><Th align="right">Tasks</Th>
                  <Th align="right">Emission</Th>
                </tr>
              </thead>
              <tbody>
                {top.map((m) => (
                  <tr key={m.uid} className="transition-colors hover:bg-surface-2/60">
                    <Td className="font-mono text-ink-3">{m.rank}</Td>
                    <Td>
                      <Link href={`/miners/${m.uid}`} className="flex items-center gap-2 text-ink-1 hover:text-accent">
                        <span className="font-medium">{m.name}</span>
                        <Badge tone="neutral">{m.profile_label}</Badge>
                      </Link>
                    </Td>
                    <Td align="right">
                      <div className="flex items-center justify-end gap-2">
                        <span className="font-mono text-ink-1">{num(m.reputation)}</span>
                        <Meter value={m.reputation} className="w-12" />
                      </div>
                    </Td>
                    <Td align="right">{pct(m.accuracy)}</Td>
                    <Td align="right">{m.task_count}</Td>
                    <Td align="right" className="font-mono text-accent">{pct(m.emission_weight, 2)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : <LoadingRow />}
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Recent verification events"
            subtitle="Streamed from the validator event bus"
            right={<Link href="/live"><Label>Live view →</Label></Link>} />
          <EventFeed limit={9} compact />
        </Card>
      </div>
    </>
  );
}

function HealthRow({ icon: Icon, label, value, tone }: {
  icon: any; label: string; value: string; tone: "positive" | "warning" | "neutral";
}) {
  const colour = tone === "positive" ? "text-positive" : tone === "warning" ? "text-warning" : "text-ink-2";
  return (
    <div className="flex items-center gap-3">
      <Icon size={14} className={colour} />
      <span className="text-[13px] text-ink-2">{label}</span>
      <span className="ml-auto text-right text-[13px] text-ink-1">{value}</span>
    </div>
  );
}
