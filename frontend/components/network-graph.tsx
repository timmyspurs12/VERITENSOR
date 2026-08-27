"use client";

import * as React from "react";
import type { GraphPayload, SubnetEvent } from "@/types";

/**
 * Force-free deterministic layout: validators on an inner ring, miners on an
 * outer ring. Edge opacity encodes how often that validator queried that miner
 * and how well the miner scored — both come from real task records.
 *
 * Nodes illuminate when a matching event arrives on the live stream, so the
 * animation is a projection of backend activity rather than decoration.
 */
export function NetworkGraph({
  data, events, height = 460,
}: { data: GraphPayload; events: SubnetEvent[]; height?: number }) {
  const [hover, setHover] = React.useState<string | null>(null);

  const active = React.useMemo(() => {
    const recent = events.slice(0, 12);
    const ids = new Set<string>();
    recent.forEach((e) => {
      if (e.miner_uid !== null && e.miner_uid !== undefined) ids.add(`m${e.miner_uid}`);
      if (e.validator_uid !== null && e.validator_uid !== undefined) ids.add(`v${e.validator_uid}`);
    });
    return ids;
  }, [events]);

  const validators = data.nodes.filter((n) => n.type === "validator");
  const miners = data.nodes.filter((n) => n.type === "miner");
  const W = 900, H = height, cx = W / 2, cy = H / 2;

  const pos = new Map<string, { x: number; y: number }>();
  validators.forEach((n, i) => {
    const a = (i / Math.max(1, validators.length)) * Math.PI * 2 - Math.PI / 2;
    pos.set(n.id, { x: cx + Math.cos(a) * 96, y: cy + Math.sin(a) * 78 });
  });
  miners.forEach((n, i) => {
    const a = (i / Math.max(1, miners.length)) * Math.PI * 2 - Math.PI / 2;
    pos.set(n.id, { x: cx + Math.cos(a) * 330, y: cy + Math.sin(a) * 190 });
  });

  const maxInteractions = Math.max(1, ...data.edges.map((e) => e.interactions));

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }}>
        {data.edges.map((e, i) => {
          const a = pos.get(e.source), b = pos.get(e.target);
          if (!a || !b) return null;
          const strength = e.interactions / maxInteractions;
          const highlighted = hover === e.source || hover === e.target;
          return (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={e.accuracy > 0.7 ? "#7DD6FA" : "#5E6773"}
              strokeWidth={highlighted ? 1.4 : 0.7}
              strokeOpacity={highlighted ? 0.7 : 0.06 + strength * 0.22} />
          );
        })}

        {miners.map((n) => {
          const p = pos.get(n.id)!;
          const r = 5 + Math.sqrt(Math.max(0, n.weight)) * 26;
          const lit = active.has(n.id);
          return (
            <g key={n.id} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}>
              {lit && <circle cx={p.x} cy={p.y} r={r + 7} fill="#7DD6FA" opacity={0.12} />}
              <circle cx={p.x} cy={p.y} r={r}
                fill={lit ? "#7DD6FA" : "#12161D"}
                stroke={(n.reputation ?? 0) > 0.6 ? "#7DD6FA" : "#3A4552"}
                strokeWidth={1.2} />
              <text x={p.x} y={p.y - r - 6} textAnchor="middle"
                className="fill-ink-3 font-mono" style={{ fontSize: 9 }}>
                {n.label}
              </text>
            </g>
          );
        })}

        {validators.map((n) => {
          const p = pos.get(n.id)!;
          const lit = active.has(n.id);
          return (
            <g key={n.id} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}>
              {lit && <rect x={p.x - 22} y={p.y - 15} width={44} height={30} rx={6}
                fill="#A8F0C6" opacity={0.14} />}
              <rect x={p.x - 17} y={p.y - 11} width={34} height={22} rx={4}
                fill="#171C24" stroke={lit ? "#A8F0C6" : "#3A4552"} strokeWidth={1.2} />
              <text x={p.x} y={p.y + 3.5} textAnchor="middle"
                className="fill-mint font-mono" style={{ fontSize: 8.5 }}>VAL</text>
              <text x={p.x} y={p.y + 24} textAnchor="middle"
                className="fill-ink-3 font-mono" style={{ fontSize: 9 }}>{n.label}</text>
            </g>
          );
        })}
      </svg>

      {hover && (
        <div className="pointer-events-none absolute left-4 top-4 rounded-md border border-line-strong bg-surface-2 px-3 py-2 shadow-pop">
          {(() => {
            const n = data.nodes.find((x) => x.id === hover)!;
            return (
              <>
                <p className="text-[13px] text-ink-1">{n.label}</p>
                <p className="font-mono text-2xs text-ink-3">
                  {n.type === "miner"
                    ? `reputation ${(n.reputation ?? 0).toFixed(3)} · ${n.tasks} tasks · weight ${((n.weight ?? 0) * 100).toFixed(2)}%`
                    : `strategy ${n.strategy} · ${n.weight} tasks scored`}
                </p>
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}
