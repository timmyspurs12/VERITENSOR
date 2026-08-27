"use client";

import clsx from "clsx";
import {
  AlertTriangle, CheckCircle2, Coins, Cpu, Radar, Send, ShieldX, Sparkles,
  Timer,
} from "lucide-react";
import Link from "next/link";
import { useEventStream } from "@/hooks/use-event-stream";
import { EmptyState } from "@/components/ui";
import { clock } from "@/lib/format";
import type { SubnetEvent } from "@/types";

const ICONS: Record<string, any> = {
  "task.generated": Sparkles,
  "task.dispatched": Send,
  "miner.responded": Cpu,
  "miner.dropped": Timer,
  "robustness.probe": Radar,
  "response.rejected": ShieldX,
  "task.verified": CheckCircle2,
  "emissions.updated": Coins,
  "epoch.closed": Coins,
};

export function eventTone(e: SubnetEvent) {
  if (e.level === "error") return "text-negative";
  if (e.level === "warning") return "text-warning";
  if (e.kind === "task.verified") return "text-positive";
  if (e.kind === "emissions.updated" || e.kind === "epoch.closed") return "text-mint";
  return "text-accent";
}

export function EventFeed({
  limit = 40, compact = false, events: provided,
}: { limit?: number; compact?: boolean; events?: SubnetEvent[] }) {
  const live = useEventStream(provided === undefined);
  const events = (provided ?? live.events).slice(0, limit);

  if (!events.length) {
    return (
      <EmptyState
        title="No events yet"
        description="Events appear as validators generate, dispatch, verify and score tasks. Create a task or run the simulation to populate the stream."
      />
    );
  }

  return (
    <ul className="divide-y divide-line/60">
      {events.map((e) => {
        const Icon = ICONS[e.kind] ?? AlertTriangle;
        return (
          <li key={e.seq} className="flex animate-fade-up items-start gap-3 px-5 py-2.5">
            <Icon size={13} className={clsx("mt-0.5 shrink-0", eventTone(e))} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] text-ink-1">
                {e.message}
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 font-mono text-2xs text-ink-3">
                <span>{clock(e.timestamp)}</span>
                <span className="text-line-hi">·</span>
                <span>{e.kind}</span>
                {e.task_id && !compact && (
                  <>
                    <span className="text-line-hi">·</span>
                    <Link href={`/tasks/${e.task_id}`} className="hover:text-accent">
                      {e.task_id}
                    </Link>
                  </>
                )}
                {e.miner_uid !== null && (
                  <>
                    <span className="text-line-hi">·</span>
                    <Link href={`/miners/${e.miner_uid}`} className="hover:text-accent">
                      miner {e.miner_uid}
                    </Link>
                  </>
                )}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
