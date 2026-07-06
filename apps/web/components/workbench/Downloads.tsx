"use client";

// Run-detail downloads (07-06/07-07): the reproducibility manifest (a small viewer +
// JSON download) and per-candidate lineage exports (CSV/SDF anchors that stream the file
// body). The manifest is written at finalize, so it's empty while a run is live — we say
// so honestly rather than showing a broken viewer. When the manifest carries a composed
// objective (config.objective_json), we render its term list as an honest legend — real
// API data, never invented per-term deltas.

import { useEffect, useState } from "react";
import { exportCsvUrl, exportSdfUrl, getManifest, manifestUrl } from "@/lib/api";
import { Eyebrow } from "./ui";

type ManifestConfig = {
  objective_json?: { terms?: { oracle: string; weight?: number; oracle_kwargs?: { task?: string } }[]; aggregator?: string } | null;
};
type Manifest = {
  git_sha?: string | null;
  model_id?: string | null;
  pytdc_version?: string | null;
  config?: ManifestConfig | null;
};

export function Downloads({
  runId,
  finalized,
}: {
  runId: number;
  finalized: boolean;
}) {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!finalized) return;
    let closed = false;
    getManifest(runId)
      .then((m) => !closed && setManifest(m as Manifest))
      .catch((e: unknown) => !closed && setErr(e instanceof Error ? e.message : String(e)));
    return () => {
      closed = true;
    };
  }, [runId, finalized]);

  const hasManifest = manifest != null && Object.keys(manifest).length > 0;
  const terms = manifest?.config?.objective_json?.terms ?? [];

  const anchorCls =
    "rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none";

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-heading text-base font-normal">Reproducibility &amp; export</h2>
        <span className="text-xs text-muted-foreground">manifest · lineage CSV/SDF</span>
      </div>

      <div className="flex flex-col gap-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <div className="flex flex-wrap items-center gap-2">
          <a href={exportCsvUrl(runId)} download className={anchorCls}>
            Download lineage (CSV)
          </a>
          <a href={exportSdfUrl(runId)} download className={anchorCls}>
            Download lineage (SDF)
          </a>
          {hasManifest && (
            <a href={manifestUrl(runId)} download={`run-${runId}-manifest.json`} className={anchorCls}>
              Download manifest (JSON)
            </a>
          )}
        </div>

        {err ? (
          <p role="alert" className="text-xs text-destructive">
            Couldn&apos;t load the manifest: {err}
          </p>
        ) : !finalized ? (
          <p className="text-xs text-muted-foreground">
            The reproducibility manifest is written when the run finalizes. Lineage exports
            reflect whatever candidates have been scored so far.
          </p>
        ) : hasManifest ? (
          <div className="flex flex-col gap-2">
            <Eyebrow>Manifest</Eyebrow>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
              <Row k="git SHA" v={manifest?.git_sha} mono />
              <Row k="model" v={manifest?.model_id} />
              <Row k="PyTDC" v={manifest?.pytdc_version} />
            </dl>
            {terms.length > 0 && (
              <div className="mt-1 flex flex-col gap-1.5">
                <Eyebrow>Objective composition</Eyebrow>
                <div className="flex flex-wrap gap-1.5">
                  {terms.map((t, i) => (
                    <span
                      key={`${t.oracle}-${i}`}
                      className="rounded-md border border-border bg-muted/60 px-1.5 py-0.5 font-mono text-[0.66rem] text-foreground"
                    >
                      {t.oracle}
                      {t.oracle_kwargs?.task ? `:${t.oracle_kwargs.task}` : ""}
                      {typeof t.weight === "number" ? ` ×${t.weight}` : ""}
                    </span>
                  ))}
                  {manifest?.config?.objective_json?.aggregator && (
                    <span className="text-[0.66rem] text-muted-foreground">
                      · {manifest.config.objective_json.aggregator.replace("_", " ")}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            No reproducibility manifest is recorded for this run — it finalized before
            manifests were introduced.
          </p>
        )}
      </div>
    </section>
  );
}

function Row({ k, v, mono = false }: { k: string; v?: string | null; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className={`truncate text-foreground ${mono ? "font-mono" : ""}`}>{v || "—"}</dd>
    </div>
  );
}
