"use client";

// LOW-FI PROTOTYPE AUC panel — throwaway. Streaming top-10-mean curve (coral =
// this run) with the Graph-GA baseline as a horizontal REFERENCE LINE + a live
// "beating by +X / behind by X" delta badge (locked product decision b). NOT a
// GA curve.

import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { CurvePoint } from "@/lib/api";

export function AucPanel({
  curve,
  baseline,
  running,
}: {
  curve: CurvePoint[];
  baseline: number;
  running: boolean;
}) {
  const latest = curve.length ? curve[curve.length - 1].top10_mean : 0;
  const delta = latest - baseline;
  const beating = delta >= 0;
  const deltaLabel = `${beating ? "+" : "−"}${Math.abs(delta).toFixed(3)}`;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={[
              "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
              beating
                ? "bg-primary/12 text-primary ring-1 ring-primary/30"
                : "bg-muted text-muted-foreground ring-1 ring-border",
            ].join(" ")}
          >
            {beating ? "Beating baseline" : "Behind baseline"} by {deltaLabel}
          </span>
        </div>
        <span className="text-xs text-muted-foreground">top-10 mean · in-silico</span>
      </div>

      <div className="mt-3 min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={curve} margin={{ top: 6, right: 8, bottom: 4, left: -12 }}>
            <XAxis
              dataKey="oracle_calls"
              type="number"
              domain={["dataMin", "dataMax"]}
              allowDecimals={false}
              tick={{ fontSize: 11 }}
              tickFormatter={(v: number) => (v >= 1000 ? `${v / 1000}k` : String(v))}
            />
            <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} width={34} />
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
          This run {running ? "(live)" : ""}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0 w-4 border-t border-dashed border-muted-foreground" />
          Graph-GA baseline (in-silico)
        </span>
      </div>
    </div>
  );
}
