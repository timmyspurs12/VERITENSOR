"use client";

import * as React from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from "recharts";

const AXIS = { stroke: "#3A4552", fontSize: 10, fontFamily: "var(--font-mono)" };
const GRID = "#1E252F";

function TooltipBox({ active, payload, label, formatter }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-sm border border-line-strong bg-surface-2 px-2.5 py-2 shadow-pop">
      {label !== undefined && (
        <p className="mb-1 font-mono text-2xs uppercase tracking-widest text-ink-3">{label}</p>
      )}
      {payload.map((p: any) => (
        <p key={p.dataKey} className="tabular font-mono text-xs text-ink-1">
          <span className="mr-2 inline-block h-2 w-2 rounded-[1px]" style={{ background: p.color || p.fill }} />
          {p.name}: {formatter ? formatter(p.value) : p.value}
        </p>
      ))}
    </div>
  );
}

export function TrendChart({
  data, xKey, series, height = 200, format, domain,
}: {
  data: any[]; xKey: string; height?: number;
  series: { key: string; label: string; color: string }[];
  format?: (v: number) => string;
  domain?: [number | "auto", number | "auto"];
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 4 }}>
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={s.color} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis {...AXIS} tickLine={false} axisLine={false} width={52}
          domain={domain ?? ["auto", "auto"]}
          tickFormatter={(v) => (format ? format(v) : String(v))} />
        <Tooltip content={<TooltipBox formatter={format} />} cursor={{ stroke: "#2A323D" }} />
        {series.map((s) => (
          <Area key={s.key} type="monotone" dataKey={s.key} name={s.label}
            stroke={s.color} strokeWidth={1.6} fill={`url(#g-${s.key})`} dot={false} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function MultiLineChart({
  data, xKey, series, height = 220, format,
}: {
  data: any[]; xKey: string; height?: number; format?: (v: number) => string;
  series: { key: string; label: string; color: string }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 4 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis {...AXIS} tickLine={false} axisLine={false} width={52}
          tickFormatter={(v) => (format ? format(v) : String(v))} />
        <Tooltip content={<TooltipBox formatter={format} />} />
        <Legend wrapperStyle={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "#99A2AF" }} />
        {series.map((s) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.label}
            stroke={s.color} strokeWidth={1.6} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BarSeries({
  data, xKey, yKey, height = 220, color = "#7DD6FA", format, colorKey,
}: {
  data: any[]; xKey: string; yKey: string; height?: number; color?: string;
  format?: (v: number) => string; colorKey?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 4 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickLine={false} axisLine={{ stroke: GRID }}
          interval={0} angle={data.length > 8 ? -35 : 0} textAnchor={data.length > 8 ? "end" : "middle"}
          height={data.length > 8 ? 52 : 28} />
        <YAxis {...AXIS} tickLine={false} axisLine={false} width={52}
          tickFormatter={(v) => (format ? format(v) : String(v))} />
        <Tooltip content={<TooltipBox formatter={format} />} cursor={{ fill: "#ffffff08" }} />
        <Bar dataKey={yKey} radius={[2, 2, 0, 0]} maxBarSize={34}>
          {data.map((row, i) => (
            <Cell key={i} fill={colorKey ? row[colorKey] : color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ComponentRadar({
  values, height = 220,
}: { values: { component: string; value: number }[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={values} outerRadius="72%">
        <PolarGrid stroke={GRID} />
        <PolarAngleAxis dataKey="component" tick={{ fill: "#99A2AF", fontSize: 10,
          fontFamily: "var(--font-mono)" }} />
        <Radar dataKey="value" stroke="#7DD6FA" fill="#7DD6FA" fillOpacity={0.16}
          strokeWidth={1.6} />
        <Tooltip content={<TooltipBox formatter={(v: number) => v.toFixed(3)} />} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

export function Sparkline({ values, color = "#7DD6FA", height = 28 }: {
  values: number[]; color?: string; height?: number;
}) {
  if (!values.length) return <div className="h-[28px]" />;
  const max = Math.max(...values, 0.000001);
  const min = Math.min(...values, 0);
  const points = values.map((v, i) => {
    const x = (i / Math.max(1, values.length - 1)) * 100;
    const y = 100 - ((v - min) / Math.max(1e-9, max - min)) * 100;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height }} className="w-full">
      <polyline points={points} fill="none" stroke={color} strokeWidth="2.4"
        vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
