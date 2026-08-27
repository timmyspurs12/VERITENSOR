"use client";

import { ArrowDown, ArrowUp, Minus, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { PageHeader } from "@/components/shell";
import {
  Badge, Card, CardHeader, EmptyState, ErrorState, Label, LoadingRow, Meter,
  SegmentedControl, Table, Td, Th,
} from "@/components/ui";
import { useMiners } from "@/hooks/use-api";
import { ms, num, pct } from "@/lib/format";
import type { MinerRow } from "@/types";

type SortKey = "rank" | "reputation" | "accuracy" | "robustness" | "calibration"
  | "latency" | "task_count" | "emission_weight";

const CATEGORIES = [
  { value: "", label: "All" }, { value: "code", label: "Code" },
  { value: "math", label: "Math" }, { value: "reasoning", label: "Reasoning" },
  { value: "data", label: "Data" },
];

export default function MinersPage() {
  const [category, setCategory] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState<SortKey>("rank");
  const [dir, setDir] = React.useState<1 | -1>(1);
  const { data, error, isLoading } = useMiners(category || undefined);

  const rows = React.useMemo(() => {
    let items = data?.items ?? [];
    if (query.trim()) {
      const q = query.toLowerCase();
      items = items.filter((m) => m.name.toLowerCase().includes(q)
        || m.profile_label.toLowerCase().includes(q));
    }
    const get = (m: MinerRow): number => {
      switch (sort) {
        case "rank": return m.rank;
        case "reputation": return -m.reputation;
        case "accuracy": return -(category ? m.category_accuracy ?? 0 : m.accuracy);
        case "robustness": return -(m.components.robustness ?? 0);
        case "calibration": return -(m.components.calibration ?? 0);
        case "latency": return m.mean_latency_ms;
        case "task_count": return -m.task_count;
        case "emission_weight": return -m.emission_weight;
      }
    };
    return [...items].sort((a, b) => (get(a) - get(b)) * dir);
  }, [data, query, sort, dir, category]);

  const toggle = (key: SortKey) => {
    if (sort === key) setDir((d) => (d === 1 ? -1 : 1));
    else { setSort(key); setDir(1); }
  };

  if (error) return <ErrorState error={String(error)} />;

  return (
    <>
      <PageHeader
        title="Miner leaderboard"
        description="Reputation is an EMA of task scores, shrunk toward a low prior until a miner has enough scored tasks. Click a miner for its full profile and failure analysis."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SegmentedControl value={category} onChange={setCategory} options={CATEGORIES} />
            <div className="flex items-center gap-2 rounded-sm border border-line-strong bg-surface-2 px-2.5 py-1.5">
              <Search size={13} className="text-ink-3" />
              <input
                value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter miners"
                className="w-32 bg-transparent text-[13px] text-ink-1 outline-none placeholder:text-ink-3"
              />
            </div>
          </div>
        }
      />

      <Card>
        <CardHeader
          title={category ? `Ranked by mean score in ${category}` : "Ranked by network reputation"}
          subtitle={`${rows.length} miners · emission weights sum to 1 across eligible miners`}
          right={<Label>{data?.total ?? 0} registered</Label>}
        />
        {isLoading ? <LoadingRow /> : rows.length === 0 ? (
          <EmptyState title="No miners match" description="Adjust the filter or category to see registered miners." />
        ) : (
          <Table>
            <thead>
              <tr>
                <SortableTh label="Rank" k="rank" sort={sort} dir={dir} onClick={toggle} />
                <Th>Miner</Th>
                <Th>Archetype</Th>
                <SortableTh label="Score" k="reputation" sort={sort} dir={dir} onClick={toggle} align="right" />
                <SortableTh label="Accuracy" k="accuracy" sort={sort} dir={dir} onClick={toggle} align="right" />
                <SortableTh label="Robustness" k="robustness" sort={sort} dir={dir} onClick={toggle} align="right" />
                <SortableTh label="Calibration" k="calibration" sort={sort} dir={dir} onClick={toggle} align="right" />
                <SortableTh label="Latency" k="latency" sort={sort} dir={dir} onClick={toggle} align="right" />
                <SortableTh label="Tasks" k="task_count" sort={sort} dir={dir} onClick={toggle} align="right" />
                <SortableTh label="Emission" k="emission_weight" sort={sort} dir={dir} onClick={toggle} align="right" />
                <Th align="right">Trend</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.uid} className="group transition-colors hover:bg-surface-2/60">
                  <Td className="font-mono text-ink-3">{m.rank}</Td>
                  <Td>
                    <Link href={`/miners/${m.uid}`}
                      className="font-medium text-ink-1 transition-colors group-hover:text-accent">
                      {m.name}
                    </Link>
                    {Object.keys(m.flags).length > 0 && (
                      <span className="ml-2 align-middle">
                        <Badge tone="warning">{Object.keys(m.flags).length} flags</Badge>
                      </span>
                    )}
                  </Td>
                  <Td><span className="text-xs text-ink-3">{m.profile_label}</span></Td>
                  <Td align="right">
                    <div className="flex items-center justify-end gap-2">
                      <span className="font-mono text-ink-1">
                        {num(category ? m.category_score ?? 0 : m.reputation)}
                      </span>
                      <Meter value={category ? m.category_score ?? 0 : m.reputation} className="w-10" />
                    </div>
                  </Td>
                  <Td align="right">{pct(category ? m.category_accuracy : m.accuracy)}</Td>
                  <Td align="right">{num(m.components.robustness ?? 0, 2)}</Td>
                  <Td align="right">{num(m.components.calibration ?? 0, 2)}</Td>
                  <Td align="right">{ms(m.mean_latency_ms)}</Td>
                  <Td align="right">{category ? m.category_tasks ?? 0 : m.task_count}</Td>
                  <Td align="right" className="font-mono text-accent">{pct(m.emission_weight, 2)}</Td>
                  <Td align="right"><Trend value={m.trend} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <p className="mt-3 text-xs leading-relaxed text-ink-3">
        Robustness and calibration are the components of the miner&apos;s most recent
        scored task. A miner below the emission floor or under the minimum sample
        size receives a zero weight — see the emissions page for exclusion reasons.
      </p>
    </>
  );
}

function SortableTh({ label, k, sort, dir, onClick, align = "left" }: {
  label: string; k: SortKey; sort: SortKey; dir: 1 | -1;
  onClick: (k: SortKey) => void; align?: "left" | "right";
}) {
  const active = sort === k;
  return (
    <Th align={align} className="cursor-pointer select-none hover:text-ink-1">
      <button onClick={() => onClick(k)} className="inline-flex items-center gap-1">
        {label}
        {active && (dir === 1 ? <ArrowUp size={10} /> : <ArrowDown size={10} />)}
      </button>
    </Th>
  );
}

function Trend({ value }: { value: number }) {
  if (Math.abs(value) < 0.005) {
    return <span className="inline-flex items-center gap-1 text-ink-3"><Minus size={11} />flat</span>;
  }
  const up = value > 0;
  return (
    <span className={`inline-flex items-center gap-1 font-mono ${up ? "text-positive" : "text-negative"}`}>
      {up ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
      {(value * 100).toFixed(1)}
    </span>
  );
}
