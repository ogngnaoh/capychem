import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// The benchmark/exploratory honesty badge (m07 slice 01). Every run surface shows
// it so an exploratory run (custom seed/oracle/objective/constraint) can never be
// read as benchmark-comparable — the G1 claim stays pristine. Exploratory uses the
// chart-4 caution tint (mirrors the Cockpit notice box), NOT the coral --primary,
// so it never reads as a positive/branded state.
//
// `compact` shortens the exploratory label to "Exploratory" for dense lists (Overview
// recent-runs, tables) where the full "· not benchmark-comparable" clause collides with
// the row label; the full clause stays in the title tooltip so the honesty claim never
// disappears.
export function ModeBadge({
  mode,
  className,
  compact = false,
}: {
  mode: string;
  className?: string;
  compact?: boolean;
}) {
  if (mode === "exploratory") {
    return (
      <Badge
        variant="outline"
        title="Exploratory run — not benchmark-comparable"
        className={cn(
          "shrink-0 whitespace-nowrap border-chart-4/40 bg-chart-4/15 text-foreground",
          className,
        )}
      >
        {compact ? "Exploratory" : "Exploratory · not benchmark-comparable"}
      </Badge>
    );
  }
  return (
    <Badge
      variant="secondary"
      title="Benchmark run — comparable to the committed Graph-GA control"
      className={cn("shrink-0 whitespace-nowrap", className)}
    >
      Benchmark
    </Badge>
  );
}
