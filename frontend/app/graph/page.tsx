"use client";

import { Network } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, Card, CardHeader, Label, LoadingRow, Stat } from "@/components/ui";
import { EventFeed } from "@/components/event-feed";
import { NetworkGraph } from "@/components/network-graph";
import { useEventStream } from "@/hooks/use-event-stream";
import { useGraph, useStats } from "@/hooks/use-api";
import { num, pct } from "@/lib/format";

export default function GraphPage() {
  const { data, isLoading } = useGraph();
  const { data: stats } = useStats();
  const { events, connected } = useEventStream();

  return (
    <>
      <PageHeader
        title="Live network graph"
        description="Validators (inner ring) query miners (outer ring). Edge weight is the real number of dispatches recorded between that pair over the last 200 tasks; node size is the miner's current emission weight. Nodes illuminate when an event referencing them arrives on the stream."
        actions={
          <Badge tone={connected ? "positive" : "warning"}>
            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-current" />
            {connected ? "streaming" : "polling"}
          </Badge>
        }
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
        <Card className="rounded-none border-0">
          <Stat label="Nodes" value={data?.nodes.length ?? "—"}
            hint={`${stats?.active_validators ?? 0} validators · ${stats?.active_miners ?? 0} miners`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Edges" value={data?.edges.length ?? "—"}
            hint={`window: last ${data?.window_tasks ?? 0} tasks`} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Network accuracy" tone="accent" value={pct(stats?.network_accuracy)} />
        </Card>
        <Card className="rounded-none border-0">
          <Stat label="Emission Gini" value={num(stats?.emission_gini, 3)} />
        </Card>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-4">
        <Card className="lg:col-span-3">
          <CardHeader title="Validator ↔ miner topology"
            subtitle="Cyan edges indicate a pairing whose mean accuracy exceeds 70%"
            right={<Network size={14} className="text-ink-3" />} />
          {isLoading || !data ? <LoadingRow /> : (
            <NetworkGraph data={data} events={events} />
          )}
          <div className="flex flex-wrap gap-4 border-t border-line px-5 py-3">
            <Legend colour="#A8F0C6" label="Validator" shape="square" />
            <Legend colour="#7DD6FA" label="Miner (size = emission weight)" />
            <Legend colour="#7DD6FA" label="High-accuracy pairing" shape="line" />
            <Legend colour="#5E6773" label="Low-accuracy pairing" shape="line" />
          </div>
        </Card>

        <Card>
          <CardHeader title="Events driving the graph" subtitle="The same bus the animation listens to" />
          <div className="max-h-[560px] overflow-y-auto">
            <EventFeed limit={50} compact />
          </div>
        </Card>
      </div>
    </>
  );
}

function Legend({ colour, label, shape = "circle" }: {
  colour: string; label: string; shape?: "circle" | "square" | "line";
}) {
  return (
    <span className="flex items-center gap-2 text-xs text-ink-3">
      {shape === "line" ? (
        <span className="h-px w-5" style={{ background: colour }} />
      ) : (
        <span className={shape === "square" ? "h-2.5 w-3.5 rounded-[2px] border" : "h-2.5 w-2.5 rounded-full border"}
          style={{ borderColor: colour }} />
      )}
      {label}
    </span>
  );
}
