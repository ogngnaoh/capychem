import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Outlet, useLocation, useParams } from "react-router";
import {
  ArrowDownToLine,
  ArrowRight,
  ChevronDown,
  GitBranch,
} from "lucide-react";
import { useStudio, StudioLink, protocolLabel } from "./StudioContext";
import { type ExperimentRun } from "./experimentModel";
import { ApiError } from "./api";
import {
  EmptyState,
  InlineError,
  LoadingState,
  NotFoundPage,
  StatusLabel,
  exportRecord,
} from "./ProductUI";
import { Modal } from "./Modal";
import { download } from "./data";
import { Button } from "@astryxdesign/core/Button";
import { StudioActionLink } from "./StudioActionLink";
const ExperimentContext = createContext<ExperimentRun | null>(null);
export function useExperiment() {
  const run = useContext(ExperimentContext);
  if (!run) throw new Error("Experiment context is missing");
  return run;
}
export function ExperimentLayout() {
  const { experimentId = "" } = useParams();
  const w = useStudio();
  const { pathname } = useLocation();
  const [loaded, setLoaded] = useState("");
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const [retry, setRetry] = useState(0);
  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const run = w.runs.find((r) => r.id === experimentId);
  useEffect(() => {
    let alive = true;
    setError("");
    setMissing(false);
    w.openRun(experimentId)
      .then(() => {
        if (alive) setLoaded(experimentId);
      })
      .catch((e) => {
        if (alive) {
          if (e instanceof ApiError && e.status === 404) setMissing(true);
          else setError(e.message);
        }
      });
    return () => {
      alive = false;
    };
  }, [experimentId, retry, w.openRun, w.demo]);
  if (missing) return <NotFoundPage experiment />;
  if (error && loaded !== experimentId)
    return (
      <section className="product-page">
        <InlineError
          message={`This experiment could not be opened. ${error}`}
          onRetry={() => setRetry((n) => n + 1)}
        />
        <EmptyState
          title="Your experiment has not been replaced"
          body="Check the local engine connection and try again."
          action={
            <StudioLink className="secondary-button" to="/engine">
              Local engine <ArrowRight size={16} />
            </StudioLink>
          }
        />
      </section>
    );
  if (loaded !== experimentId || !run)
    return (
      <section className="product-page">
        <LoadingState label="Opening experiment…" />
      </section>
    );
  const preset = w.presets.find((p) => p.id === run.config.targetPreparationId);
  const root = `/experiments/${experimentId}`;
  const save = async () => {
    setExporting(true);
    setExportError("");
    try {
      if (w.demo) {
        const recorded = w.recordedExperiments.find(
          (r) => r.experiment.id === run.id,
        );
        if (recorded) {
          const response = await fetch(recorded.export_url);
          if (!response.ok) throw new Error("Recorded export unavailable");
          const original = await response.json();
          download(
            `capychem-${run.id}.json`,
            JSON.stringify(
              {
                ...original,
                recorded: true,
                local_review: {
                  scope: "Browser annotations on a recorded result",
                  decisions: w.generated.map((c) => ({
                    candidate_id: c.id,
                    pinned: w.pins.includes(c.id),
                    notes: w.notes[c.id] ?? "",
                    preferred_pose_id: w.preferredPoses[c.id] ?? null,
                  })),
                },
              },
              null,
              2,
            ),
          );
        } else
          download(
            "capychem-recorded-experiment.json",
            JSON.stringify(
              {
                recorded: true,
                experiment: run,
                candidates: w.generated,
                notes: w.notes,
                pins: w.pins,
                provenance: w.batchProvenance,
              },
              null,
              2,
            ),
          );
      } else await exportRecord(experimentId);
      setExportOpen(false);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };
  return (
    <ExperimentContext.Provider value={run}>
      <section className={`experiment-page experiment-v5 ${pathname === root ? "experiment-editor" : ""}`}>
        <header className="experiment-page-header">
          <div className="experiment-title-row">
            <div>
              <nav className="breadcrumb" aria-label="Breadcrumb">
                <StudioLink to="/experiments">Experiments</StudioLink>
                <span aria-hidden="true">/</span>
                <h1 title={run.name}>{run.name}</h1>
              </nav>
              <div className="experiment-subtitle">
                <span>
                  {preset
                    ? `CDK2 · receptor ${preset.receptor_pdb_id}`
                    : (run.config.targetPreparationId ??
                      "CDK2 · receptor 1H1P")}
                </span>
                <StatusLabel status={run.status} />
                {run.recorded && <span>Recorded example</span>}
              </div>
            </div>
            <div className="page-actions">
              <Button
                label="Export"
                variant="secondary"
                icon={<ArrowDownToLine size={15} />}
                onClick={() => {
                  setExportError("");
                  setExportOpen(true);
                }}
              />
              <StudioActionLink
                label="New round"
                variant="primary"
                icon={<GitBranch size={15} />}
                to={`/experiments/new?from=${experimentId}`}
              />
            </div>
          </div>
          <div className="experiment-tabs-row">
            <nav className="experiment-tabs" aria-label="Experiment views">
              {[
                ["Workspace", ""],
                ["Activity", "/activity"],
                ["Compare", "/compare"],
              ].map(([label, suffix]) => (
                <StudioLink
                  key={label}
                  to={root + suffix}
                  className={pathname === root + suffix ? "selected" : ""}
                  aria-current={pathname === root + suffix ? "page" : undefined}
                >
                  {label}
                  {label === "Compare" &&
                    w.pins.filter((id) => w.generated.some((c) => c.id === id))
                      .length > 0 && (
                      <span>
                        {
                          w.pins.filter((id) =>
                            w.generated.some((c) => c.id === id),
                          ).length
                        }
                      </span>
                    )}
                </StudioLink>
              ))}
            </nav>
            <details className="design-rules">
              <summary>
                Design rules
                <ChevronDown size={14} />
              </summary>
              <div>
                <h3>Preserve the {preset?.parent.name ?? "declared"} parent</h3>
                <p>
                  {preset?.description ??
                    "Keep the declared parent atoms and bonds while exploring a side group in a fixed protein pocket."}
                </p>
                <dl>
                  <div>
                    <dt>Property profile</dt>
                    <dd>
                      MW ≤ {run.config.maxMolecularWeight ?? 450}, cLogP ≤{" "}
                      {run.config.maxLogP}, rotors ≤{" "}
                      {run.config.maxRotatableBonds ?? 8}
                    </dd>
                  </div>
                  <div>
                    <dt>Evaluation</dt>
                    <dd>
                      Up to {run.config.maxCandidates} candidates ·{" "}
                      {run.config.conformers} attempts each
                    </dd>
                  </div>
                  <div>
                    <dt>Protocol</dt>
                    <dd>{protocolLabel(run.config.protocol)}</dd>
                  </div>
                </dl>
                <StudioLink className="text-link" to={root + "/activity"}>
                  Inspect settings and activity
                  <ArrowRight size={14} />
                </StudioLink>
              </div>
            </details>
          </div>
        </header>
        {error && (
          <InlineError message={error} onRetry={() => setRetry((n) => n + 1)} />
        )}
        <Outlet />
      </section>
      {exportOpen && (
        <Modal title="Export experiment" onClose={() => setExportOpen(false)}>
          <p className="export-intro">
            The record contains the immutable specification, candidates,
            decisions, evidence and artifact links. Molecular files retain their
            exact evaluated coordinates.
          </p>
          {exportError && <InlineError message={exportError} />}
          <button
            className="export-option"
            disabled={exporting}
            onClick={() => void save()}
          >
            <ArrowDownToLine size={20} />
            <span>
              <strong>
                {exporting ? "Preparing export…" : "Experiment record"}
              </strong>
              <small>
                JSON · inputs, results, notes and artifact references
              </small>
            </span>
            <ArrowRight size={17} />
          </button>
          <p className="field-help">
            Download an individual pose or capture the current view from the
            molecular workspace.
          </p>
        </Modal>
      )}
    </ExperimentContext.Provider>
  );
}
