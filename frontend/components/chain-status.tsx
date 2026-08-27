"use client";

import { CircleCheck, CircleX, ExternalLink, Link2Off } from "lucide-react";
import { Badge, Card, CardHeader, Label, LoadingRow } from "@/components/ui";
import { useChainStatus } from "@/hooks/use-api";

const CHECK_LABELS: Record<string, string> = {
  sdk_installed: "Bittensor SDK installed",
  sdk_supported: "SDK generation supported",
  netuid_configured: "SUBNET_NETUID configured",
  chain_reachable: "Chain endpoint reachable",
  subnet_exists: "Subnet exists on chain",
  wallet_files_present: "Wallet + hotkey present",
  hotkey_registered: "Hotkey registered on subnet",
};

const REMEDY: Record<string, string> = {
  sdk_installed: "pip install -r requirements-bittensor.txt",
  sdk_supported: "pip install -U bittensor",
  netuid_configured: "set SUBNET_NETUID in .env",
  chain_reachable: "check network access to the endpoint",
  subnet_exists: "btcli subnet list --subtensor.network test",
  wallet_files_present: "btcli wallet new_coldkey / new_hotkey",
  hotkey_registered: "btcli subnet register --netuid <N>  (burns TAO)",
};

/**
 * Read-only Bittensor status. Renders the backend's preflight verbatim: a
 * green tick appears only for a prerequisite that genuinely holds, and the
 * panel states plainly when nothing has been deployed.
 */
export function ChainStatusPanel() {
  const { data, isLoading } = useChainStatus();

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader title="Bittensor status" subtitle="Read-only chain probe" />
        <LoadingRow label="Probing chain" />
      </Card>
    );
  }

  const checks = data.preflight?.checks ?? {};
  const ready = Boolean(data.ready_to_submit_weights);
  const note = data.preflight?.subnet_note;

  return (
    <Card>
      <CardHeader
        title="Bittensor status"
        subtitle="Read-only probe — this panel never signs or submits anything"
        right={
          <div className="flex items-center gap-2">
            {data.cached && (
              <span className="font-mono text-2xs text-ink-3">
                probed {Math.round(data.age_seconds ?? 0)}s ago
              </span>
            )}
            <Badge tone={ready ? "positive" : data.reachable ? "warning" : "negative"}>
              {ready ? "ready to submit weights"
                : data.reachable ? "chain reachable · not deployed"
                  : "chain unreachable"}
            </Badge>
          </div>
        }
      />

      <div className="grid gap-px overflow-hidden border-b border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
        <Cell label="SDK" value={data.sdk.installed
          ? `${data.sdk.version} (${data.sdk.generation})` : "not installed"} />
        <Cell label="Network" value={data.configured.network} />
        <Cell label="Netuid" value={data.configured.netuid || "unset"} />
        <Cell label="Block" value={data.preflight?.block ?? "—"} />
      </div>

      {data.preflight?.subnet && (
        <div className="grid gap-px overflow-hidden border-b border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          <Cell label="Subnet" value={data.preflight.subnet.name} />
          <Cell label="UIDs" value={`${data.preflight.subnet.num_uids}/${data.preflight.subnet.max_uids}`} />
          <Cell label="Tempo" value={data.preflight.subnet.tempo} />
          <Cell label="Registration burn" value={data.preflight.registration_cost ?? "—"} />
        </div>
      )}

      <ul className="divide-y divide-line/60">
        {Object.entries(checks).map(([key, ok]) => (
          <li key={key} className="flex flex-wrap items-center gap-3 px-5 py-2.5">
            {ok
              ? <CircleCheck size={14} className="shrink-0 text-positive" />
              : <CircleX size={14} className="shrink-0 text-negative" />}
            <span className="text-[13px] text-ink-1">{CHECK_LABELS[key] ?? key}</span>
            {!ok && (
              <code className="ml-auto max-w-full truncate rounded-xs border border-line bg-bg px-2 py-0.5 font-mono text-2xs text-ink-3">
                {key === "subnet_exists" && note
                  ? "no subnet selected yet"
                  : REMEDY[key] ?? "see docs/DEPLOYMENT_CHECKLIST.md"}
              </code>
            )}
          </li>
        ))}
      </ul>

      {note && (
        <p className="border-t border-line px-5 py-2.5 text-xs leading-relaxed text-ink-3">
          {note}
        </p>
      )}

      {!data.reachable && data.reason && (
        <div className="flex items-start gap-2 border-t border-line px-5 py-3">
          <Link2Off size={13} className="mt-0.5 shrink-0 text-negative" />
          <p className="font-mono text-2xs leading-relaxed text-ink-3">{data.reason}</p>
        </div>
      )}

      <p className="border-t border-line px-5 py-3 text-xs leading-relaxed text-ink-3">
        {ready
          ? "All prerequisites are satisfied: a validator started with chain.submit_weights=true will publish weights on chain."
          : "VERITENSOR is not deployed on a Bittensor subnet. The unmet prerequisites above are real and require operator action (wallet creation, funding, registration) — see "}
        {!ready && (
          <span className="inline-flex items-center gap-1 text-accent">
            docs/DEPLOYMENT_CHECKLIST.md <ExternalLink size={10} />
          </span>
        )}
      </p>
    </Card>
  );
}

function Cell({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="bg-surface-1 px-4 py-3">
      <Label>{label}</Label>
      <p className="mt-1 truncate font-mono text-[13px] text-ink-1">{value}</p>
    </div>
  );
}
