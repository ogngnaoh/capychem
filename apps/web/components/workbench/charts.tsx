"use client";

// Shared workbench charts — on-token via CSS vars (no hardcoded hex). This-run =
// chart-1 (coral); Graph-GA baseline = muted-foreground dashed reference line;
// Compare B = chart-2 (blue). Ported from the CP2-approved hi-fi prototype
// (app/proto/_chart.tsx); AucPanel's baseline is now nullable (the run snapshot's
// graph_ga_baseline may be absent).

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { AucOverlayPoint, CurvePoint } from "@/lib/api";

const Y_TICKS = [0, 0.25, 0.5, 0.75, 1];
const fmtK = (v: number) => (v >= 1000 ? `${v / 1000}k` : String(v));
const fmt2 = (v: number) => v.toFixed(2);
const axisTick = { fontSize: 11, fill: "var(--color-muted-foreground)" };

export function AucPanel({
  curve,
  baseline,
  running,
}: {
  curve: CurvePoint[];
  baseline: number | null;
  running: boolean;
}) {
  const latest = curve.length ? curve[curve.length - 1].top10_mean : 0;
  const hasBaseline = baseline !== null;
  const delta = hasBaseline ? latest - baseline : 0;
  const beating = delta >= 0;
  const deltaLabel = `${beating ? "+" : "−"}${Math.abs(delta).toFixed(3)}`;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-baseline justify-between gap-2">
        {hasBaseline ? (
          <span
            className={[
              "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
              beating
                ? "bg-primary/12 text-foreground ring-1 ring-primary/30"
                : "bg-muted text-muted-foreground ring-1 ring-border",
            ].join(" ")}
          >
            {beating ? "Beating baseline" : "Behind baseline"} by {deltaLabel}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">
            no Graph-GA baseline for this task
          </span>
        )}
        <span className="text-xs text-muted-foreground">top-10 mean · in-silico</span>
      </div>

      <div className="mt-3 min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={curve} margin={{ top: 8, right: 10, bottom: 2, left: -8 }}>
            <CartesianGrid vertical={false} stroke="var(--color-border)" />
            <XAxis
              dataKey="oracle_calls"
              type="number"
              domain={["dataMin", "dataMax"]}
              allowDecimals={false}
              tick={axisTick}
              tickLine={false}
              axisLine={{ stroke: "var(--color-border)" }}
              tickFormatter={fmtK}
            />
            <YAxis
              domain={[0, 1]}
              ticks={Y_TICKS}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
              width={36}
              tickFormatter={fmt2}
            />
            {hasBaseline && (
              <ReferenceLine
                y={baseline}
                stroke="var(--color-muted-foreground)"
                strokeDasharray="5 4"
                label={{
                  value: `Graph-GA ${baseline.toFixed(3)}`,
                  position: "insideBottomRight",
                  fontSize: 10,
                  fill: "var(--color-muted-foreground)",
                }}
              />
            )}
            <Line
              type="monotone"
              dataKey="top10_mean"
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-primary" />
          This run{running ? " (live)" : ""}
        </span>
        {hasBaseline && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0 w-4 border-t border-dashed border-muted-foreground" />
            Graph-GA baseline (in-silico)
          </span>
        )}
      </div>
    </div>
  );
}

// Compare overlay: A = chart-1 (coral), B = chart-2 (blue).
export function CompareChart({
  overlay,
  labelA,
  labelB,
}: {
  overlay: AucOverlayPoint[];
  labelA: string;
  labelB: string;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={overlay} margin={{ top: 8, right: 10, bottom: 2, left: -8 }}>
            <CartesianGrid vertical={false} stroke="var(--color-border)" />
            <XAxis
              dataKey="oracle_calls"
              type="number"
              domain={["dataMin", "dataMax"]}
              allowDecimals={false}
              tick={axisTick}
              tickLine={false}
              axisLine={{ stroke: "var(--color-border)" }}
              tickFormatter={fmtK}
            />
            <YAxis
              domain={[0, 1]}
              ticks={Y_TICKS}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
              width={36}
              tickFormatter={fmt2}
            />
            <Line
              type="monotone"
              dataKey="a"
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="b"
              stroke="var(--color-chart-2)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-chart-1" />
          {labelA}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-chart-2" />
          {labelB}
        </span>
        <span className="ml-auto">top-10 mean vs oracle calls · in-silico</span>
      </div>
    </div>
  );
}
