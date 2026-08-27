"use client";

import { useEffect, useRef, useState } from "react";
import type { SubnetEvent } from "@/types";

/**
 * Subscribes to the backend SSE feed (/api/events/stream). Events are produced
 * by the real validator pipeline; if the stream drops we fall back to polling
 * so the view degrades instead of freezing.
 */
export function useEventStream(enabled = true, capacity = 120) {
  const [events, setEvents] = useState<SubnetEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const seqRef = useRef(0);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | undefined;

    const push = (incoming: SubnetEvent[]) => {
      if (!incoming.length) return;
      seqRef.current = Math.max(seqRef.current, ...incoming.map((e) => e.seq));
      setEvents((prev) => [...incoming.reverse(), ...prev].slice(0, capacity));
    };

    const source = new EventSource("/api/events/stream");
    source.onopen = () => !cancelled && setConnected(true);
    source.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as SubnetEvent;
        if (event.seq > seqRef.current) push([event]);
      } catch {
        /* keep-alive comment frames are ignored */
      }
    };
    source.onerror = () => {
      setConnected(false);
      source.close();
      if (!poll) {
        poll = setInterval(async () => {
          const res = await fetch(`/api/events?limit=40&after_seq=${seqRef.current}`);
          if (res.ok) push((await res.json()) as SubnetEvent[]);
        }, 5000);
      }
    };
    return () => {
      cancelled = true;
      source.close();
      if (poll) clearInterval(poll);
    };
  }, [enabled, capacity]);

  return { events, connected };
}
