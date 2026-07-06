// Molecule-quality + population-health display primitives (07-05/07-08). Pure and
// null-safe: `quality` is null while a run is live (populated at finalize) and any key
// may be absent, so every reader guards. Never color-only — each chip carries a label.

import type { MoleculeQuality } from "@/lib/api";

function Chip({
  label,
  tone = "neutral",
  title,
}: {
  label: string;
  tone?: "neutral" | "pass" | "warn";
  title?: string;
}) {
  const cls =
    tone === "warn"
      ? "border-chart-4/40 bg-chart-4/15 text-foreground"
      : tone === "pass"
        ? "border-chart-3/40 bg-chart-3/10 text-foreground"
        : "border-border bg-muted/60 text-muted-foreground";
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[0.66rem] font-medium ${cls}`}
    >
      {label}
    </span>
  );
}

const fmt = (v: number | undefined, digits = 2) =>
  typeof v === "number" ? v.toFixed(digits) : "—";

// Compact per-molecule quality: QED, SA, Lipinski/Veber pass-fail, and PAINS/Brenk
// structural-alarm flags (a flag = bad). Returns a "computing…" chip while quality is
// null (live run, pre-finalize) so a live tile never looks broken.
export function QualityBadges({ quality }: { quality?: MoleculeQuality | null }) {
  if (quality == null) {
    return <Chip label="quality computing…" title="Quality is scored at finalize." />;
  }
  const chips: React.ReactNode[] = [];
  if (typeof quality.qed === "number") {
    chips.push(<Chip key="qed" label={`QED ${fmt(quality.qed)}`} title="Drug-likeness (0–1)" />);
  }
  if (typeof quality.sa_score === "number") {
    chips.push(
      <Chip key="sa" label={`SA ${fmt(quality.sa_score)}`} title="Synthetic accessibility (1 easy → 10 hard)" />,
    );
  }
  if (typeof quality.lipinski_pass === "boolean") {
    chips.push(
      <Chip
        key="lipinski"
        label={quality.lipinski_pass ? "Lipinski ✓" : "Lipinski ✕"}
        tone={quality.lipinski_pass ? "pass" : "warn"}
        title="Lipinski rule-of-five"
      />,
    );
  }
  if (typeof quality.veber_pass === "boolean") {
    chips.push(
      <Chip
        key="veber"
        label={quality.veber_pass ? "Veber ✓" : "Veber ✕"}
        tone={quality.veber_pass ? "pass" : "warn"}
        title="Veber oral-bioavailability rules"
      />,
    );
  }
  // Structural alarms: a true flag is bad (the molecule matches a PAINS/Brenk pattern).
  if (quality.pains === true) {
    chips.push(<Chip key="pains" label="PAINS ⚠" tone="warn" title="Matches a PAINS alert" />);
  }
  if (quality.brenk === true) {
    chips.push(<Chip key="brenk" label="Brenk ⚠" tone="warn" title="Matches a Brenk alert" />);
  }
  if (chips.length === 0) {
    return <Chip label="no quality metrics" />;
  }
  return <div className="flex flex-wrap items-center gap-1">{chips}</div>;
}

const pct = (v: number | null | undefined) =>
  typeof v === "number" ? `${Math.round(v * 100)}%` : null;

// Run-level population health: internal diversity + novelty vs the gen-0 seed. Both are
// null while a run is live (finalize-only) and novelty can be null on a resumed run;
// each reads "computing…" rather than a misleading 0.
export function PopulationHealth({
  diversity,
  novelty,
  live,
}: {
  diversity?: number | null;
  novelty?: number | null;
  live: boolean;
}) {
  const items: { label: string; value: string; help: string }[] = [
    {
      label: "Diversity",
      value: pct(diversity) ?? (live ? "computing…" : "—"),
      help: "Mean pairwise dissimilarity across the final population (higher = more varied).",
    },
    {
      label: "Novelty",
      value: pct(novelty) ?? (live ? "computing…" : "—"),
      help: "Share of the population structurally distinct from the seed compounds.",
    },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-8 gap-y-2 rounded-xl bg-card px-4 py-3 ring-1 ring-foreground/10">
      <div className="text-[0.68rem] font-medium tracking-[0.1em] text-muted-foreground uppercase">
        Population health
      </div>
      <dl className="flex flex-wrap items-center gap-x-8 gap-y-2">
        {items.map((it) => (
          <div key={it.label} className="flex items-baseline gap-2">
            <dt className="text-xs text-muted-foreground" title={it.help}>
              {it.label}
            </dt>
            <dd className="text-sm font-semibold tabular-nums">{it.value}</dd>
          </div>
        ))}
      </dl>
      <span className="ml-auto text-[0.7rem] text-muted-foreground">
        internal diversity · novelty vs seed (in-silico)
      </span>
    </div>
  );
}
