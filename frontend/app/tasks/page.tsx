"use client";

import { CircleCheck, CircleX, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { useSWRConfig } from "swr";
import { PageHeader } from "@/components/shell";
import {
  Badge, Button, Card, CardHeader, EmptyState, ErrorState, Label, LoadingRow,
  Select, Table, Td, Th,
} from "@/components/ui";
import { useTasks, useValidators } from "@/hooks/use-api";
import { api } from "@/lib/api";
import { categoryLabel, ms, num, pct, timeAgo } from "@/lib/format";

const PAGE = 25;

export default function TaskExplorerPage() {
  const [category, setCategory] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [validator, setValidator] = React.useState("");
  const [difficulty, setDifficulty] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const [creating, setCreating] = React.useState(false);
  const [notice, setNotice] = React.useState<string | null>(null);
  const { mutate } = useSWRConfig();
  const { data: validators } = useValidators();

  const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (category) query.set("category", category);
  if (status) query.set("status", status);
  if (validator) query.set("validator_uid", validator);
  if (difficulty === "easy") { query.set("min_difficulty", "1"); query.set("max_difficulty", "3"); }
  if (difficulty === "normal") { query.set("min_difficulty", "4"); query.set("max_difficulty", "6"); }
  if (difficulty === "hard") { query.set("min_difficulty", "7"); query.set("max_difficulty", "8"); }
  if (difficulty === "adversarial") { query.set("min_difficulty", "9"); }

  const { data, error, isLoading } = useTasks(query.toString());

  const generate = async () => {
    setCreating(true);
    setNotice(null);
    try {
      const task = await api.createTask({ category: category || undefined });
      setNotice(`Generated ${task.task_id} — ${task.responses.length} miners responded, `
        + `${task.responses.filter((r) => r.correct).length} correct.`);
      setOffset(0);
      await mutate((key) => typeof key === "string" && key.startsWith("/api/"));
    } catch (e) {
      setNotice(`Failed: ${String(e)}`);
    } finally {
      setCreating(false);
    }
  };

  if (error) return <ErrorState error={String(error)} />;

  const total = data?.total ?? 0;

  return (
    <>
      <PageHeader
        title="Verification tasks"
        description="Every task carries a hidden ground truth that is never returned by these endpoints while the task is open. Task text differs on every draw because generators are parameterised by a random seed."
        actions={
          <Button variant="primary" onClick={generate} disabled={creating}>
            {creating ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />}
            Generate & dispatch task
          </Button>
        }
      />

      {notice && (
        <div className="mb-4 rounded-md border border-accent/30 bg-accent/[0.07] px-4 py-2.5 text-[13px] text-accent">
          {notice}
        </div>
      )}

      <Card>
        <CardHeader
          title="Filters"
          subtitle="Query the executed task log"
          right={<Label>{total} tasks</Label>}
        />
        <div className="flex flex-wrap items-center gap-3 px-5 py-3.5">
          <Select label="Family" value={category} onChange={(v) => { setCategory(v); setOffset(0); }}
            options={[{ value: "", label: "All" }, { value: "code", label: "Code security" },
              { value: "math", label: "Mathematics" }, { value: "reasoning", label: "Reasoning" },
              { value: "data", label: "Data analysis" }]} />
          <Select label="Status" value={status} onChange={(v) => { setStatus(v); setOffset(0); }}
            options={[{ value: "", label: "All" }, { value: "scored", label: "Scored" },
              { value: "verified", label: "Verified" }, { value: "failed", label: "Failed" }]} />
          <Select label="Difficulty" value={difficulty} onChange={(v) => { setDifficulty(v); setOffset(0); }}
            options={[{ value: "", label: "All" }, { value: "easy", label: "Easy 1–3" },
              { value: "normal", label: "Normal 4–6" }, { value: "hard", label: "Hard 7–8" },
              { value: "adversarial", label: "Adversarial 9–10" }]} />
          <Select label="Validator" value={validator} onChange={(v) => { setValidator(v); setOffset(0); }}
            options={[{ value: "", label: "All" },
              ...(validators ?? []).map((v) => ({ value: String(v.uid), label: v.name }))]} />
        </div>
      </Card>

      <Card className="mt-4">
        {isLoading ? <LoadingRow /> : !data?.items.length ? (
          <EmptyState title="No tasks match these filters"
            description="Loosen a filter, or generate a new task to run the full pipeline now."
            action={<Button size="sm" onClick={generate}>Generate task</Button>} />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Task</Th><Th>Family</Th><Th align="right">Diff</Th><Th>Kind</Th>
                  <Th>Verification</Th><Th>Validator</Th><Th align="right">Responses</Th>
                  <Th align="right">Correct</Th><Th align="right">Consensus</Th>
                  <Th align="right">Age</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => (
                  <tr key={t.task_id} className="group transition-colors hover:bg-surface-2/60">
                    <Td>
                      <Link href={`/tasks/${t.task_id}`}
                        className="font-mono text-xs text-ink-2 group-hover:text-accent">
                        {t.task_id}
                      </Link>
                      <p className="mt-0.5 max-w-[280px] truncate text-2xs text-ink-3">
                        {t.prompt_excerpt}
                      </p>
                    </Td>
                    <Td><span className="text-xs">{categoryLabel[t.category]}</span></Td>
                    <Td align="right">{t.difficulty}/10</Td>
                    <Td><Badge tone={t.kind === "adversarial" ? "warning" : "neutral"}>{t.kind}</Badge></Td>
                    <Td><span className="font-mono text-2xs text-ink-3">{t.verification_type}</span></Td>
                    <Td><span className="text-xs">{t.validator_name}</span></Td>
                    <Td align="right">{t.responses}</Td>
                    <Td align="right">
                      <span className={t.correct_responses ? "text-positive" : "text-negative"}>
                        {t.correct_responses}
                      </span>
                    </Td>
                    <Td align="right">{pct(t.consensus?.verification_confidence, 0)}</Td>
                    <Td align="right"><span className="text-xs text-ink-3">{timeAgo(t.created_at)}</span></Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="flex items-center justify-between border-t border-line px-5 py-3">
              <Label>
                {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
              </Label>
              <div className="flex gap-2">
                <Button size="sm" disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
                <Button size="sm" disabled={offset + PAGE >= total}
                  onClick={() => setOffset(offset + PAGE)}>Next</Button>
              </div>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
