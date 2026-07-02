// LOW-FI PROTOTYPE shared components — throwaway. Structural/neutral only:
// existing tokens, coral restrained to primary action / live state / this-run.

import { LOOP_STEPS } from "./_mock";

// A neutral placeholder for a 2D molecular structure. Low-fi recommendation is a
// clean motif; slice 02/03 should render RDKit SVG server-side (see decisions).
export function MoleculeTile({ size = 56 }: { size?: number }) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-md border border-dashed bg-muted/40"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg
        width={size * 0.5}
        height={size * 0.5}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        className="text-muted-foreground"
      >
        {/* stylised hexagonal ring — reads as "structure", not a real molecule */}
        <polygon points="12,3 20,7.5 20,16.5 12,21 4,16.5 4,7.5" />
        <circle cx="12" cy="12" r="3.5" />
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
    <div className="rounded-lg bg-card px-3 py-2.5 ring-1 ring-foreground/10">
      <div className="text-[0.7rem] tracking-wide text-muted-foreground uppercase">
        {label}
      </div>
      <div
        className={`mt-0.5 text-xl font-semibold tabular-nums ${
          accent ? "text-primary" : ""
        }`}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

// A small progress bar built from tokens (no new styling primitives).
export function Meter({ value, max }: { value: number; max: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
    </div>
  );
}

// propose -> score -> ANALYZE -> redesign -> stop. `analyze` is emphasised as the
// differentiator. Pass `activeStep` on the cockpit for a live current-step pip;
// omit it on the Overview for a static teaching diagram.
export function LoopDiagram({
  activeStep,
  compact = false,
}: {
  activeStep?: string;
  compact?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-stretch gap-1.5" role="list">
      {LOOP_STEPS.map((step, i) => {
        const isAnalyze = step.key === "analyze";
        const isActive = activeStep === step.key;
        return (
          <div key={step.key} className="flex items-stretch gap-1.5" role="listitem">
            <div
              className={[
                "flex flex-col justify-center rounded-lg border text-center transition-colors",
                compact ? "px-2.5 py-1.5" : "px-3.5 py-3 min-w-24",
                isAnalyze
                  ? "border-primary/60 bg-primary/10"
                  : "border-border bg-card",
                isActive ? "ring-2 ring-primary" : "",
              ].join(" ")}
            >
              <div
                className={[
                  compact ? "text-xs" : "text-sm",
                  "font-medium",
                  isAnalyze ? "text-primary" : "text-foreground",
                ].join(" ")}
              >
                {step.label}
              </div>
              {isAnalyze && !compact && (
                <div className="mt-0.5 text-[0.7rem] leading-tight text-primary/80">
                  the differentiator
                </div>
              )}
              {isActive && (
                <div className="mt-0.5 text-[0.7rem] text-muted-foreground">
                  · current step
                </div>
              )}
            </div>
            {i < LOOP_STEPS.length - 1 && (
              <div
                className="flex items-center text-muted-foreground"
                aria-hidden="true"
              >
                →
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// First-class in-silico honesty label (N6). Never a real-world efficacy claim.
export function InSilicoTag({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[0.7rem] text-muted-foreground ${className}`}
    >
      in-silico · oracle score
    </span>
  );
}

// Thin ribbon marking these routes as disposable low-fi wireframes.
export function ProtoRibbon() {
  return (
    <div className="border-b border-dashed border-border bg-muted/40 px-6 py-1 text-center text-[0.7rem] tracking-wide text-muted-foreground uppercase">
      Low-fi wireframe · disposable prototype · structure &amp; hierarchy only
    </div>
  );
}
