// HI-FI PROTOTYPE shared components — on-token (globals.css), coral restrained to
// primary action / live state / this-run series. Structural/neutral everywhere else.

import { LOOP_STEPS } from "./_mock";

// Small uppercase eyebrow — encodes section context, set in the utility register.
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-medium tracking-[0.16em] text-muted-foreground uppercase">
      {children}
    </div>
  );
}

// A neutral placeholder for a 2D molecular structure. Low-fi/hi-fi both use a clean
// motif; slice 03 renders RDKit SVG server-side (see 01-decisions.md §5).
export function MoleculeTile({ size = 52 }: { size?: number }) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-md border border-dashed border-border bg-muted/50"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg
        width={size * 0.46}
        height={size * 0.46}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.1"
        className="text-muted-foreground"
      >
        <polygon points="12,3 20,7.5 20,16.5 12,21 4,16.5 4,7.5" />
        <circle cx="12" cy="12" r="3.4" />
        <line x1="20" y1="7.5" x2="23" y2="6" />
        <line x1="4" y1="16.5" x2="1" y2="18" />
      </svg>
    </div>
  );
}

export function StatTile({
  label,
  value,
  sub,
  accent = false,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-xl bg-card px-3.5 py-3 ring-1 ring-foreground/10">
      <div className="text-[0.68rem] font-medium tracking-[0.1em] text-muted-foreground uppercase">
        {label}
      </div>
      <div
        className={`mt-1 text-2xl leading-none font-semibold tabular-nums ${
          accent ? "text-primary" : "text-foreground"
        }`}
      >
        {value}
      </div>
      {sub && <div className="mt-1.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

// A slim progress bar built from tokens.
export function Meter({ value, max }: { value: number; max: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-primary transition-[width]"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// The loop as a left-to-right sequence of chips reading like a sentence:
// propose → score → ANALYZE → redesign → stop. `analyze` is emphasised (coral) as
// the differentiator. `activeStep` (cockpit only) marks the live step; omit it on
// the Overview for a static teaching diagram.
export function LoopDiagram({
  activeStep,
  compact = false,
}: {
  activeStep?: string;
  compact?: boolean;
}) {
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-2">
      {LOOP_STEPS.map((step, i) => {
        const isAnalyze = step.key === "analyze";
        const isActive = activeStep === step.key;
        return (
          <li key={step.key} className="flex items-center gap-1">
            <div
              className={[
                "inline-flex items-center gap-1.5 rounded-full border transition-colors",
                compact ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm",
                isAnalyze
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border bg-card text-foreground",
                isActive ? "ring-2 ring-primary ring-offset-1 ring-offset-background" : "",
              ].join(" ")}
            >
              {isActive && (
                <span
                  className="size-1.5 rounded-full bg-primary motion-safe:animate-pulse"
                  aria-hidden="true"
                />
              )}
              <span className={isAnalyze ? "font-medium" : ""}>{step.label}</span>
            </div>
            {i < LOOP_STEPS.length - 1 && (
              <span className="px-0.5 text-muted-foreground" aria-hidden="true">
                →
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

// First-class in-silico honesty label (N6). Never a real-world efficacy claim.
export function InSilicoTag({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-0.5 text-[0.7rem] text-muted-foreground ${className}`}
    >
      <span className="size-1 rounded-full bg-muted-foreground" aria-hidden="true" />
      in-silico · oracle score
    </span>
  );
}

// Status chip — never color-only (label carries meaning); coral reserved for the
// live "running" state.
export function StatusChip({ status }: { status: string }) {
  const live = status === "running";
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        live
          ? "bg-primary/12 text-primary ring-1 ring-primary/30"
          : "bg-muted text-muted-foreground ring-1 ring-border",
      ].join(" ")}
    >
      {live && (
        <span
          className="size-1.5 rounded-full bg-primary motion-safe:animate-pulse"
          aria-hidden="true"
        />
      )}
      {status}
    </span>
  );
}

// Thin ribbon marking these routes as disposable prototypes.
export function ProtoRibbon() {
  return (
    <div className="border-b border-dashed border-border bg-muted/40 px-6 py-1 text-center text-[0.68rem] tracking-[0.14em] text-muted-foreground uppercase">
      Prototype · hi-fi on-token · mock data
    </div>
  );
}
