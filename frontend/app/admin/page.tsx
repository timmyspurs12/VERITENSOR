"use client";

import { ShieldAlert, Terminal } from "lucide-react";
import useSWR from "swr";
import { PageHeader } from "@/components/shell";
import {
  Badge, Card, CardHeader, ErrorState, Label, LoadingRow, Table, Td, Th,
} from "@/components/ui";
import { ChainStatusPanel } from "@/components/chain-status";
import { fetcher } from "@/lib/api";
import { clock, num } from "@/lib/format";

export default function AdminPage() {
  const { data, error, isLoading } = useSWR<Record<string, any>>(
    "/api/admin/diagnostics", fetcher, { refreshInterval: 15000 });

  return (
    <>
      <PageHeader
        title="Diagnostics"
        description="Operator view of the running process. This route is disabled when ENVIRONMENT=production and requires the ADMIN_API_KEY header whenever one is configured."
        actions={<Badge tone="warning"><ShieldAlert size={10} /> admin-guarded</Badge>}
      />

      <div className="mb-4">
        <ChainStatusPanel />
      </div>

      {error ? (
        <ErrorState error={`${error} — diagnostics are disabled in production or require an admin key.`} />
      ) : isLoading || !data ? <Card><LoadingRow /></Card> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader title="Runtime settings" subtitle="Secret values are never included" />
            <Table>
              <tbody>
                {Object.entries(data.settings ?? {}).map(([k, v]) => (
                  <tr key={k}>
                    <Td className="font-mono text-xs text-ink-3">{k}</Td>
                    <Td className="font-mono text-xs text-ink-1">{String(v)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader title="Boot report" subtitle="How the seeded network was produced" />
            <Table>
              <tbody>
                {Object.entries(data.boot ?? {}).map(([k, v]) => (
                  <tr key={k}>
                    <Td className="font-mono text-xs text-ink-3">{k}</Td>
                    <Td className="font-mono text-xs text-ink-1">{String(v)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader title="Anti-gaming guards" subtitle="Per-validator guard state" />
            <Table>
              <thead>
                <tr><Th>Validator</Th><Th align="right">Tracked tasks</Th>
                  <Th align="right">Submissions</Th><Th align="right">Miners tracked</Th></tr>
              </thead>
              <tbody>
                {Object.entries(data.guards ?? {}).map(([uid, g]: any) => (
                  <tr key={uid}>
                    <Td className="text-ink-1">validator {uid}</Td>
                    <Td align="right">{g.tracked_tasks}</Td>
                    <Td align="right">{g.recorded_submissions}</Td>
                    <Td align="right">{g.miners_tracked}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader title="Registered generators"
              subtitle={`${(data.generators ?? []).length} task generators loaded`}
              right={<Terminal size={13} className="text-ink-3" />} />
            <div className="flex flex-wrap gap-1.5 px-5 py-4">
              {(data.generators ?? []).map((g: string) => (
                <Badge key={g}>{g}</Badge>
              ))}
            </div>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader title="Recent warnings and errors"
              subtitle="Structured events at warning level or above"
              right={<Label>{(data.recent_warnings ?? []).length} entries</Label>} />
            <Table>
              <thead>
                <tr><Th>Time</Th><Th>Level</Th><Th>Kind</Th><Th>Message</Th>
                  <Th>Task</Th><Th align="right">Miner</Th></tr>
              </thead>
              <tbody>
                {(data.recent_warnings ?? []).map((e: any) => (
                  <tr key={e.seq}>
                    <Td className="font-mono text-2xs text-ink-3">{clock(e.timestamp)}</Td>
                    <Td><Badge tone={e.level === "error" ? "negative" : "warning"}>{e.level}</Badge></Td>
                    <Td className="font-mono text-xs">{e.kind}</Td>
                    <Td className="text-xs">{e.message}</Td>
                    <Td className="font-mono text-2xs text-ink-3">{e.task_id ?? "—"}</Td>
                    <Td align="right">{e.miner_uid ?? "—"}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
