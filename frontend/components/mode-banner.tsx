"use client";

import { Radio, ShieldAlert, Cable } from "lucide-react";
import { Badge } from "@/components/ui";
import { useChainStatus, useStats } from "@/hooks/use-api";

/**
 * Always-visible statement of what the user is looking at.
 *
 * VERITENSOR distinguishes three mutually exclusive modes and never blends
 * them:
 *
 *   LOCAL_SIMULATION   in-process engine; no wallets, no transport, no chain
 *   LOCAL_NEURONS      separate neuron processes, real wallets, btauth/1
 *                      signed HTTP; still no chain
 *   BITTENSOR_TESTNET  neurons registered on chain; weights submitted on chain
 *
 * The mode comes from the backend adapter, not from a build flag, so it cannot
 * drift from what the server is actually doing.
 */
export function ModeBanner({ compact = false }: { compact?: boolean }) {
  const { data } = useStats(20000);
  const { data: chain } = useChainStatus();
  const info = data?.mode_info;
  const mode = info?.mode ?? "LOCAL_SIMULATION";
  const onChain = Boolean(info?.on_chain);

  const label =
    mode === "LOCAL_SIMULATION" ? "LOCAL SIMULATION"
      : mode === "LOCAL_NEURONS" ? "LOCAL NEURONS"
        : mode === "BITTENSOR_MAINNET" ? "BITTENSOR MAINNET"
          : "BITTENSOR TESTNET";

  const tone = onChain ? "positive" : mode === "LOCAL_NEURONS" ? "accent" : "warning";
  const Icon = onChain ? Radio : mode === "LOCAL_NEURONS" ? Cable : ShieldAlert;

  if (compact) {
    return (
      <Badge tone={tone}>
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-current" />
        {label}
      </Badge>
    );
  }

  const description = onChain
    ? `Connected to ${info?.chain_endpoint} · netuid ${info?.netuid} · block ${info?.block}. Weights on this page were submitted on chain.`
    : mode === "LOCAL_NEURONS"
      ? "Separate miner/validator processes with real Bittensor wallets over btauth/1 signed HTTP. No chain connection — weights are computed, not submitted."
      : "Deterministic in-process subnet. Every metric is produced by the real scoring pipeline running against simulated miners — no chain data, no TAO.";

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-surface-1/60 px-4 py-2 text-xs md:px-6">
      <Icon size={13} className={onChain ? "text-positive" : mode === "LOCAL_NEURONS" ? "text-accent" : "text-warning"} />
      <span className="font-mono text-2xs uppercase tracking-[0.14em] text-ink-2">
        {label}
      </span>
      <span className="hidden text-ink-3 sm:inline">{description}</span>
      <span className="ml-auto hidden items-center gap-3 font-mono text-2xs text-ink-3 lg:flex">
        <span>netuid {info?.netuid ?? "—"}</span>
        <span className="text-line-hi">/</span>
        <span>
          SDK {info?.bittensor_sdk_installed
            ? `${info.bittensor_sdk_version ?? "?"} ${info.bittensor_sdk_generation ?? ""}`.trim()
            : "absent"}
        </span>
        <span className="text-line-hi">/</span>
        <span>
          chain {chain === undefined ? "…" : chain.reachable ? "reachable" : "unreachable"}
        </span>
        <span className="text-line-hi">/</span>
        <span>wallet {info?.wallet_configured ? "configured" : "unset"}</span>
      </span>
    </div>
  );
}
