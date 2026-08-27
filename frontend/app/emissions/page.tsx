"use client";

import { Ban, Coins, TrendingUp } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/shell";
import {
  Badge, Card, CardHeader, ErrorState, Label, LoadingRow, Meter, Stat, Table,
  Td, Th,
} from "@/components/ui";
import { BarSeries, Sparkline, TrendChart } from "@/components/charts";
import { useEmissions } from "@/hooks/use-api";
import { num, pct } from "@/lib/format";

export default function EmissionsPage() {
  const { data, error, isLoading } = useEmissions();
  if (error) return <ErrorState error={String(error)} />;
  if (isLoading || !data) return <Card><LoadingRow /></Card>;

  const eligible = data.items.filter((i) => i.eligible);
  const excluded = data.items.filter((i) => !i.eligible);
  const epochSeries = data.epochs.map((e) => ({
    epoch: `E${e.epoch}`, gini: e.emission_gini, score: e.network_score,
  }));

  return (
    <>
      <PageHeader
        title="Emission weights"
        description="Reputation is converted into a normalised weight vector that always sums to one. This is the vector a Bittensor validator would submit with set_weights."
        actions={<Badge tone="accent"><Coins size={10} /> Σ = {num(data.total_weight, 6)}</Badge>}
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
        <Card className="rounded-none border-0">
          <Stat label="Eligible miners" value={data.eligible}
            hint={`${excluded.length} excluded by policy`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Concentration (Gini)" value={num(data.gini, 3)} tone="accent"
            hint={`cap ${pct(data.policy.max_share, 0)} per miner`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Emission floor" value={num(data.policy.floor_score, 2)}
            hint="minimum reputation to earn" />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Sharpening temperature" value={num(data.policy.temperature, 1)}
            hint={`min ${data.policy.min_tasks} scored tasks`} />
        </Card>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Current distribution"
            subtitle="Grey bars are miners excluded by the eligibility rules" />
          <div className="p-4">
            <BarSeries height={260}
              data={data.items.slice(0, 16).map((i) => ({
                name: i.name.split("-")[0], weight: i.emission_weight,
                fill: i.eligible ? "#7DD6FA" : "#2A323D",
              }))}
              xKey="name" yKey="weight" colorKey="fill"
              format={(v) => `${(v * 100).toFixed(1)}%`} />
          </div>
        </Card>

        <Card>
          <CardHeader title="Reputation → emission" subtitle="The transformation, stage by stage" />
          <ol className="space-y-3 px-5 py-4 text-[13px] leading-relaxed text-ink-2">
            {[["Raw task score", "Weighted sum of the five graded dimensions, minus penalties."],
              ["Reputation smoothing", "EMA over task history, shrunk toward a prior until the sample is large enough."],
              ["Eligibility filter", `Reject miners with < ${data.policy.min_tasks} tasks or reputation < ${data.policy.floor_score}.`],
              ["Floor subtraction", "Only the surplus above the floor competes for weight."],
              ["Temperature sharpening", `Surplus raised to the power ${data.policy.temperature} so quality gaps widen.`],
              ["Normalise & cap", `Scale to sum 1, then clip any miner above ${pct(data.policy.max_share, 0)} and redistribute.`],
            ].map(([t, b], i) => (
              <li key={t} className="flex gap-3">
                <span className="font-mono text-2xs text-ink-3">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <p className="font-medium text-ink-1">{t}</p>
                  <p className="text-xs text-ink-3">{b}</p>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Weight ledger" subtitle="Per-miner weight, eligibility and trajectory" />
          <Table>
            <thead>
              <tr>
                <Th>Miner</Th><Th align="right">Reputation</Th><Th align="right">Tasks</Th>
                <Th align="right">Weight</Th><Th>Share</Th><Th>Trajectory</Th><Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((i) => (
                <tr key={i.uid} className="hover:bg-surface-2/60">
                  <Td>
                    <Link href={`/miners/${i.uid}`} className="text-ink-1 hover:text-accent">{i.name}</Link>
                  </Td>
                  <Td align="right" className="font-mono">{num(i.reputation)}</Td>
                  <Td align="right">{i.task_count}</Td>
                  <Td align="right" className="font-mono text-accent">{pct(i.emission_weight, 3)}</Td>
                  <Td className="w-24"><Meter value={i.emission_weight * 4} /></Td>
                  <Td className="w-28">
                    <Sparkline values={i.history.length ? i.history : [0]}
                      color={i.eligible ? "#7DD6FA" : "#3A4552"} />
                  </Td>
                  <Td>
                    {i.eligible ? <Badge tone="positive">eligible</Badge>
                      : <Badge tone="warning"><Ban size={9} />{i.exclusion_reason ?? "excluded"}</Badge>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card>
          <CardHeader title="Concentration over epochs"
            subtitle="Gini of the weight vector against mean network reputation" />
          <div className="p-4">
            {epochSeries.length ? (
              <TrendChart data={epochSeries} xKey="epoch" height={240} format={(v) => v.toFixed(2)}
                series={[
                  { key: "gini", label: "Emission Gini", color: "#EFC468" },
                  { key: "score", label: "Mean reputation", color: "#A8F0C6" },
                ]} />
            ) : <LoadingRow />}
          </div>
          <p className="border-t border-line px-5 py-3 text-xs leading-relaxed text-ink-3">
            A rising Gini with a rising mean reputation is the healthy signal: the
            network is getting better and the best miners are being separated from
            the rest. A rising Gini with a flat mean would indicate capture.
          </p>
        </Card>
      </div>
    </>
  );
}
