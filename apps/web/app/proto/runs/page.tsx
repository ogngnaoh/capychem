"use client";

// HI-FI PROTOTYPE — Runs (browse). Dense, scannable table with a status filter,
// re-skinned onto the shell + tokens. Mock data; slice 03 wires the live /runs API.

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RUNS_LIST } from "../_mock";
import { Eyebrow, StatusChip } from "../_ui";

const FILTERS = ["all", "running", "exhausted", "plateaued", "stopped", "errored"] as const;

export default function RunsProto() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");

  const rows = useMemo(
    () => (filter === "all" ? RUNS_LIST : RUNS_LIST.filter((r) => r.status === filter)),
    [filter],
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Eyebrow>Runs</Eyebrow>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="font-heading text-2xl font-normal tracking-tight">
            All optimization runs
          </h1>
          <span className="text-sm text-muted-foreground">
            {rows.length} of {RUNS_LIST.length} · every score in-silico
          </span>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by status">
        {FILTERS.map((f) => {
          const active = filter === f;
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              aria-pressed={active}
              className={[
                "rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                active
                  ? "bg-foreground text-background"
                  : "border border-border text-muted-foreground hover:bg-muted hover:text-foreground",
              ].join(" ")}
            >
              {f}
            </button>
          );
        })}
      </div>

      <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Run</TableHead>
              <TableHead>Objective</TableHead>
              <TableHead>Strategy</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Best score</TableHead>
              <TableHead className="text-right">Oracle calls</TableHead>
              <TableHead className="pr-4 text-right">Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.run_id} className="cursor-pointer">
                <TableCell className="pl-4">
                  <Link
                    href="/proto/workbench"
                    className="font-medium tabular-nums underline-offset-4 hover:underline"
                  >
                    {r.run_id}
                  </Link>
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {r.task}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {r.mutation_strategy === "llm" ? "LLM proposer" : "Graph-GA"}
                </TableCell>
                <TableCell>
                  <StatusChip status={r.status} />
                </TableCell>
                <TableCell className="text-right font-semibold tabular-nums">
                  {r.best_score?.toFixed(4) ?? "—"}
                </TableCell>
                <TableCell className="text-right text-sm tabular-nums text-muted-foreground">
                  {r.oracle_calls.toLocaleString()} / {r.budget.toLocaleString()}
                </TableCell>
                <TableCell className="pr-4 text-right font-mono text-xs text-muted-foreground">
                  {r.started_at}
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                  No {filter} runs yet. Start one from the launcher.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
