"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listRuns, type RunListItem } from "@/lib/api";

type SortKey = "started_at" | "best_score" | "oracle_calls" | "status";
type Order = "asc" | "desc";

function formatRelativeTime(iso: string): string {
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function strategyLabel(s: string): string {
  return s === "llm" ? "LLM" : "Graph-GA";
}

function statusVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "errored") return "destructive";
  if (status === "running") return "default";
  return "secondary";
}

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "status", label: "Status" },
  { key: "best_score", label: "Best score" },
  { key: "oracle_calls", label: "Calls / budget" },
  { key: "started_at", label: "Started" },
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

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-heading font-normal">Runs</h1>
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← Launch a run
        </Link>
      </header>

      <div className="flex items-center justify-between gap-4">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Status</span>
          <select
            aria-label="Status filter"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">All</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="outline"
          size="sm"
          disabled={selected.length !== 2}
          onClick={() => router.push(`/compare?a=${selected[0]}&b=${selected[1]}`)}
        >
          Compare ({selected.length}/2)
        </Button>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="rounded-xl ring-1 ring-foreground/10 bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Run</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>Strategy</TableHead>
              {COLUMNS.map((c) => (
                <TableHead
                  key={c.key}
                  className={
                    c.key === "best_score" || c.key === "oracle_calls" ? "text-right" : undefined
                  }
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
              <TableRow>
                <TableCell colSpan={8} className="text-center text-muted-foreground">
                  No runs yet.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => {
                const isSelected = selected.includes(r.run_id);
                return (
                  <TableRow
                    key={r.run_id}
                    onClick={() => router.push(`/runs/${r.run_id}`)}
                    className="cursor-pointer data-[state=selected]:bg-accent"
                    data-state={isSelected ? "selected" : undefined}
                  >
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`select run ${r.run_id}`}
                        checked={isSelected}
                        disabled={selected.length >= 2 && !isSelected}
                        onChange={() => toggleSelect(r.run_id)}
                        className="size-4 accent-foreground cursor-pointer"
                      />
                    </TableCell>
                    <TableCell className="tabular-nums text-muted-foreground">
                      #{r.run_id}
                    </TableCell>
                    <TableCell className="font-medium">{r.task}</TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {strategyLabel(r.mutation_strategy)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(r.status)}>{r.status}</Badge>
                    </TableCell>
                    <TableCell className="tabular-nums text-right">
                      {r.best_score === null ? "—" : r.best_score.toFixed(4)}
                    </TableCell>
                    <TableCell className="tabular-nums text-muted-foreground text-right">
                      {r.oracle_calls} / {r.budget}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatRelativeTime(r.started_at)}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </main>
  );
}
