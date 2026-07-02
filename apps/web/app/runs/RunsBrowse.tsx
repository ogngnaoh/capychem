"use client";

// Runs (browse) — dense, scannable table over GET /runs, ported from app/proto/runs and
// wired live. Status pills filter server-side, headers sort server-side, and a two-row
// compare-select routes to /compare. Every score is an in-silico oracle score (N6).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listRuns, type RunListItem } from "@/lib/api";
import { Eyebrow, StatusChip } from "@/components/workbench/ui";

type SortKey = "started_at" | "best_score" | "oracle_calls" | "status";
type Order = "asc" | "desc";

function formatRelativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return iso;
  const secs = Math.round((Date.now() - t) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

const strategyLabel = (s: string) => (s === "llm" ? "LLM proposer" : "Graph-GA");

const SORTABLE: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "status", label: "Status" },
  { key: "best_score", label: "Best score", align: "right" },
  { key: "oracle_calls", label: "Oracle calls", align: "right" },
  { key: "started_at", label: "Started", align: "right" },
];

export function RunsBrowse() {
  const router = useRouter();
  const [rows, setRows] = useState<RunListItem[]>([]);
  const [sort, setSort] = useState<SortKey>("started_at");
  const [order, setOrder] = useState<Order>("desc");
  const [status, setStatus] = useState<string>("");
  const [statuses, setStatuses] = useState<string[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns({ sort, order, status: status || undefined })
      .then((data) => {
        setRows(data);
        setStatuses((prev) =>
          Array.from(new Set([...prev, ...data.map((r) => r.status)])).sort(),
        );
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [sort, order, status]);

  function toggleSort(key: SortKey) {
    if (key === sort) setOrder(order === "desc" ? "asc" : "desc");
    else {
      setSort(key);
      setOrder("desc");
    }
  }

  function toggleSelect(id: number) {
    setSelected((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : prev.length < 2
          ? [...prev, id]
          : prev,
    );
  }

  const arrow = (key: SortKey) => (key === sort ? (order === "desc" ? " ↓" : " ↑") : "");
  const filters = ["all", ...statuses];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Eyebrow>Runs</Eyebrow>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="font-heading text-2xl font-normal tracking-tight">
            All optimization runs
          </h1>
          <span className="text-sm text-muted-foreground">
            {rows.length} {rows.length === 1 ? "run" : "runs"} · every score in-silico
          </span>
        </div>
      </div>

      {/* Status filter + compare action */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          className="flex flex-wrap items-center gap-1.5"
          role="group"
          aria-label="Filter by status"
        >
          {filters.map((f) => {
            const active = (f === "all" && status === "") || status === f;
            return (
              <button
                key={f}
                type="button"
                onClick={() => setStatus(f === "all" ? "" : f)}
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
        <button
          type="button"
          disabled={selected.length !== 2}
          onClick={() => router.push(`/compare?a=${selected[0]}&b=${selected[1]}`)}
          className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          Compare ({selected.length}/2)
        </button>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-8 pl-4" />
              <TableHead>Run</TableHead>
              <TableHead>Objective</TableHead>
              <TableHead>Strategy</TableHead>
              {SORTABLE.map((c) => (
                <TableHead
                  key={c.key}
                  className={[c.align === "right" ? "text-right" : "", c.key === "started_at" ? "pr-4" : ""].join(" ")}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort(c.key)}
                    className="cursor-pointer font-medium text-muted-foreground hover:text-foreground"
                  >
                    {c.label}
                    {arrow(c.key)}
                  </button>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                  No {status || "matching"} runs yet. Start one from the launcher.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => {
                const isSelected = selected.includes(r.run_id);
                return (
                  <TableRow
                    key={r.run_id}
                    onClick={() => router.push(`/runs/${r.run_id}`)}
                    className="cursor-pointer data-[state=selected]:bg-muted"
                    data-state={isSelected ? "selected" : undefined}
                  >
                    <TableCell className="pl-4" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`select run ${r.run_id}`}
                        checked={isSelected}
                        disabled={selected.length >= 2 && !isSelected}
                        onChange={() => toggleSelect(r.run_id)}
                        className="size-4 accent-foreground cursor-pointer"
                      />
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/runs/${r.run_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-medium tabular-nums underline-offset-4 hover:underline"
                      >
                        {r.run_id}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {r.task}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {strategyLabel(r.mutation_strategy)}
                    </TableCell>
                    <TableCell>
                      <StatusChip status={r.status} />
                    </TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">
                      {r.best_score === null ? "—" : r.best_score.toFixed(4)}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums text-muted-foreground">
                      {r.oracle_calls.toLocaleString()} / {r.budget.toLocaleString()}
                    </TableCell>
                    <TableCell className="pr-4 text-right text-xs text-muted-foreground">
                      {formatRelativeTime(r.started_at)}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
