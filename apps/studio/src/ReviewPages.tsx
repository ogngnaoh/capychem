import { useEffect, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  GitBranch,
  Pin,
  Square,
  TriangleAlert,
} from "lucide-react";
import { useExperiment } from "./ExperimentLayout";
import { useStudio, StudioLink, protocolLabel } from "./StudioContext";
import { request, API_BASE } from "./api";
import { isActive } from "./experimentModel";
import { RunActivity, type RunEvent } from "./RunActivity";
import {
  EmptyState,
  InlineError,
  LoadingState,
  readableDate,
  exportRecord,
} from "./ProductUI";
import { selectedCandidate } from "./WorkspacePage";
import { StudioActionLink } from "./StudioActionLink";
import { displayNumber } from "./data";
import {
  candidateExplanation,
  candidateStatus,
  objectiveStatus,
  poseIdentity,
} from "./candidateReview";
type Attempt = {
  id: string;
  number: number;
  status: string;
  error?: string;
  started_at: string;
  finished_at?: string;
  report_artifact_id?: string;
  counts?: Record<string, number>;
  outcome?: Record<string, unknown>;
};
export function ActivityPage() {
  const run = useExperiment(),
    w = useStudio();
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [retry, setRetry] = useState(0);
  const recorded = w.recordedExperiments.find(
    (r) => r.experiment.id === run.id,
  );
  const active = isActive(run);
  const stageIndex = ["prepare", "generate", "evaluate", "review"].indexOf(
    run.stage,
  );
  useEffect(() => {
    if (w.demo) {
      if (recorded) setAttempts(recorded.attempts as Attempt[]);
      return;
    }
    const controller = new AbortController();
    request<{ items: Attempt[] }>(`/experiments/${run.id}/attempts`, {
      signal: controller.signal,
    })
      .then((d) => {
        setAttempts(d.items);
        setError("");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [run.id, run.status, run.latestSequence, w.demo, retry, recorded]);
  return (
    <div className="activity-page flow-v5">
      <div
        className={`activity-outcome ${run.status === "failed" ? "failed" : ""}`}
      >
        <div>
          {active ? (
            <span className="activity-live-dot" />
          ) : run.status === "failed" ? (
            <TriangleAlert size={21} />
          ) : run.status === "cancelled" ? (
            <Square size={19} />
          ) : (
            <Check size={21} />
          )}
          <div role="status" aria-label="Calculation status" aria-atomic="true">
            <h2>
              {active
                ? run.status === "queued"
                  ? "Waiting for the local worker"
                  : "Calculation in progress"
                : run.status === "failed"
                  ? "The calculation stopped"
                  : run.status === "cancelled"
                    ? "Experiment cancelled"
                    : run.status === "completed_with_errors"
                      ? "Completed with calculation errors"
                      : "Calculation completed"}
            </h2>
            <p>
              {run.message ??
                (active
                  ? "This page shows persisted stages and candidate counts from the worker."
                  : `${run.completedCandidates ?? 0} candidates evaluated. ${run.objectiveHits ?? 0} ${(run.objectiveHits ?? 0) === 1 ? "meets" : "meet"} the protocol’s contact hypothesis.`)}
            </p>
          </div>
        </div>
        {active && !w.demo ? (
          <Button
            label={cancelling ? "Requesting…" : "Cancel experiment"}
            variant="secondary"
            icon={<Square size={13} />}
            isDisabled={
              cancelling ||
              Boolean(run.message?.startsWith("Cancellation requested"))
            }
            onClick={async () => {
              setCancelling(true);
              await w.cancelRun(run.id);
              setCancelling(false);
            }}
          />
        ) : (
          <StudioActionLink to={`/experiments/${run.id}`} label="Inspect candidates" variant="primary" endContent={<ArrowRight size={16} />} />
        )}
      </div>
      <div className="activity-columns">
        <section>
          <ol className="calculation-stages">
            {[
              [
                "prepare",
                "Prepare inputs",
                "Validate the request and the fixed protein preparation.",
              ],
              [
                "generate",
                "Propose and screen",
                "Keep all proposals, with reasons for screening outcomes.",
              ],
              [
                "evaluate",
                "Evaluate poses",
                "Prepare states, embed, refine and check each admitted candidate.",
              ],
              [
                "review",
                "Review evidence",
                "Preserve coordinates, contacts, checks and the final outcome.",
              ],
            ].map(([id, title, body], i) => (
              <li
                key={id}
                aria-current={stageIndex === i && active ? "step" : undefined}
                className={
                  stageIndex === i && active
                    ? "current"
                    : stageIndex > i || (!active && run.stage === "review")
                      ? "finished"
                      : ""
                }
              >
                <span className="stage-step-icon">
                  {stageIndex > i || (!active && run.stage === "review") ? (
                    <Check size={16} />
                  ) : (
                    i + 1
                  )}
                </span>
                <div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  {id === "evaluate" && (
                    <small>
                      {run.completedCandidates ?? "—"} evaluated
                      {run.totalCandidates !== undefined
                        ? ` / ${run.totalCandidates} scheduled`
                        : ""}{" "}
                      · {run.poseFailureCount ?? "—"} pose errors ·{" "}
                      {run.embeddingFailureCount ?? "—"} embedding errors
                    </small>
                  )}
                </div>
              </li>
            ))}
          </ol>
          {w.demo && !recorded ? (
            <div className="info-block">
              <p>
                This recorded example preserves the completed result. Live event
                streaming requires the local API.
              </p>
            </div>
          ) : (
            <RunActivity
              experimentId={run.id}
              active={active}
              recordedEvents={recorded?.events as RunEvent[] | undefined}
            />
          )}
          <section className="attempt-history">
            <h2>Execution attempts</h2>
            <p className="section-description">
              A reclaimed job keeps earlier attempts separately. Results from
              different attempts are never combined.
            </p>
            {error && (
              <InlineError
                message={error}
                onRetry={() => setRetry((n) => n + 1)}
              />
            )}{" "}
            {w.demo && !recorded ? (
              <p>Recorded batch · original local calculation</p>
            ) : attempts.length === 0 ? (
              <p className="field-help">
                {active
                  ? "No worker attempt has started yet."
                  : "No execution attempts were recorded."}
              </p>
            ) : (
              attempts.map((a) => (
                <details key={a.id} className="attempt-item">
                  <summary>
                    <strong>Attempt {a.number}</strong>
                    <span>{a.status.replaceAll("_", " ")}</span>
                    <time>{readableDate(a.started_at)}</time>
                  </summary>
                  <div>
                    {a.error && <InlineError message={a.error} />}
                    <dl>
                      <div>
                        <dt>Attempt ID</dt>
                        <dd>
                          <code>{a.id}</code>
                        </dd>
                      </div>
                      <div>
                        <dt>Finished</dt>
                        <dd>
                          {a.finished_at
                            ? readableDate(a.finished_at)
                            : "In progress"}
                        </dd>
                      </div>
                    </dl>
                    <pre>
                      {JSON.stringify(
                        { counts: a.counts, outcome: a.outcome },
                        null,
                        2,
                      )}
                    </pre>
                    {!w.demo && (
                      <StudioLink
                        className="text-link"
                        to={`/experiments/${run.id}?attempt=${a.id}`}
                      >
                        Inspect this attempt
                        <ArrowRight size={15} />
                      </StudioLink>
                    )}
                    {a.report_artifact_id && !w.demo && (
                      <a
                        className="text-link"
                        href={
                          recorded
                            ? ((recorded as any).artifact_urls?.[
                                a.report_artifact_id
                              ] ??
                              `${API_BASE}/artifacts/${a.report_artifact_id}`)
                            : `${API_BASE}/artifacts/${a.report_artifact_id}`
                        }
                        download
                      >
                        <ArrowDownToLine size={15} />
                        Download attempt report
                      </a>
                    )}
                  </div>
                </details>
              ))
            )}
          </section>
        </section>
        <aside className="activity-settings">
          <h2>Experiment record</h2>
          <dl>
            <div>
              <dt>Created</dt>
              <dd>{readableDate(run.createdAt)}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>
                {run.config.source === "libinvent"
                  ? "LibInvent"
                  : "Supplied candidates"}
              </dd>
            </div>
            <div>
              <dt>Time in calculation</dt>
              <dd>
                {run.elapsedSeconds === undefined
                  ? "Not started"
                  : `${Math.round(run.elapsedSeconds)} seconds`}
              </dd>
            </div>
            <div>
              <dt>Protocol</dt>
              <dd>{protocolLabel(run.config.protocol)}</dd>
            </div>
            <div>
              <dt>Experiment ID</dt>
              <dd>
                <code>{run.id}</code>
              </dd>
            </div>
          </dl>
          {run.parentId && (
            <StudioLink
              className="text-link"
              to={`/experiments/${run.parentId}`}
            >
              <GitBranch size={15} />
              Open parent experiment
            </StudioLink>
          )}
          <details className="resolved-spec">
            <summary>Resolved settings</summary>
            <pre>{JSON.stringify(run.spec ?? run.config, null, 2)}</pre>
          </details>
          {!w.demo && (
            <Button
              label="Export full record"
              variant="secondary"
              icon={<ArrowDownToLine size={15} />}
              onClick={() =>
                void exportRecord(run.id).catch((e) => setError(e.message))
              }
            />
          )}
          <StudioLink
            className="text-link"
            to={`/experiments/new?from=${run.id}`}
          >
            Use settings for a new round <ArrowRight size={15} />
          </StudioLink>
          <p className="field-help">
            Completion means the declared calculation finished. It does not
            establish improved binding or experimental activity.
          </p>
        </aside>
      </div>
    </div>
  );
}
export function ComparePage() {
  const run = useExperiment(),
    w = useStudio();
  const all = w.generated
    .filter((c) => w.pins.includes(c.id))
    .map((c) => selectedCandidate(c, w.preferredPoses[c.id]));
  const [baselineId, setBaselineId] = useState("");
  const [comparisonId, setComparisonId] = useState("");
  const baseline = all.find((c) => c.id === baselineId) ?? all[0];
  const other =
    all.find((c) => c.id === comparisonId && c.id !== baseline?.id) ??
    all.find((c) => c.id !== baseline?.id);
  const selected = [baseline, other].filter(
    (candidate) => candidate !== undefined,
  );
  const delta = (value: number, base: number, digits = 2) => {
    if (!Number.isFinite(value) || !Number.isFinite(base))
      return "Difference unavailable";
    const difference = Number((value - base).toFixed(digits));
    return `${difference > 0 ? "+" : ""}${difference.toFixed(digits)}`;
  };
  if (!all.length)
    return (
      <EmptyState
        icon={<Pin size={26} />}
        title="Pin candidates to compare"
        body="Pin candidates from the workspace to review their selected poses, property tradeoffs and notes together."
        action={
          <StudioActionLink to={`/experiments/${run.id}`} label="Open workspace" variant="primary" endContent={<ArrowRight size={16} />} />
        }
      />
    );
  return (
    <section className="compare-page flow-v5">
      <header className="section-heading">
        <div>
          <h2>Pinned candidates</h2>
          <p className="section-description">
            Compare preferred poses and calculated properties. The baseline is
            your comparison reference, not a predicted winner.
          </p>
        </div>
        <span>{all.length} pinned</span>
      </header>
      <div className="compare-selectors">
        <label>
          Comparison baseline
          <select
            aria-label="Comparison baseline"
            value={baseline.id}
            onChange={(e) => setBaselineId(e.target.value)}
          >
            {all.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        {other && <span className="flow-comparison-versus" aria-hidden="true">vs</span>}
        {other && (
          <label>
            Compare with
            <select
              aria-label="Compare with"
              value={other.id}
              onChange={(e) => setComparisonId(e.target.value)}
            >
              {all
                .filter((c) => c.id !== baseline.id)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </select>
          </label>
        )}
      </div>
      <p className="comparison-delta-context">
        Difference from <strong>{baseline.name}</strong> · Molecular weight,
        calculated logP and rotatable bonds only. Differences use unrounded
        values. Lower is not automatically better.
      </p>
      <div
        className={`comparison-grid ${selected.length === 1 ? "comparison-single" : "comparison-pair"}`}
      >
        {selected.map((c) => (
          <article className="comparison-candidate" key={c.id}>
            <div>
              <h3>{c.name}</h3>
              <button
                className="icon-button"
                aria-label={`Unpin ${c.name}`}
                onClick={() => void w.togglePin(c.id)}
              >
                <Pin size={16} />
              </button>
            </div>
            <div className="comparison-identity">
              <span>
                {c.id === baseline.id
                  ? "Comparison baseline"
                  : `Compared with ${baseline.name}`}
              </span>
              <strong>{poseIdentity(c)}</strong>
              <span className={c.reviewReady ? "text-teal" : "muted"}>
                {candidateStatus(c)}
              </span>
            </div>
            {c.depictionUrl && (
              <img src={c.depictionUrl} alt={`${c.name} molecular structure`} />
            )}
            {!c.reviewReady && (
              <p className="comparison-explanation">
                {candidateExplanation(c)}
              </p>
            )}
            <dl>
              <div>
                <dt>Geometry</dt>
                <dd>
                  {c.checks === "pass"
                    ? "Pass"
                    : c.checks === "fail"
                      ? "Check failed"
                      : "Not evaluated"}
                </dd>
              </div>
              <div>
                <dt>Predicted Asp86 contact</dt>
                <dd>{objectiveStatus(c)}</dd>
              </div>
              <div>
                <dt>Vina score</dt>
                <dd>
                  {displayNumber(c.score)}
                  {c.score === undefined ? "" : " kcal/mol"}
                </dd>
              </div>
              <div>
                <dt>Molecular weight</dt>
                <dd>
                  {displayNumber(c.mw)} g/mol
                  <small
                    className="property-delta"
                    aria-hidden={c.id === baseline.id}
                  >
                    {c.id !== baseline.id
                      ? `${delta(c.mw, baseline.mw)} g/mol`
                      : " "}
                  </small>
                </dd>
              </div>
              <div>
                <dt>Calculated logP</dt>
                <dd>
                  {displayNumber(c.clogp)}
                  <small
                    className="property-delta"
                    aria-hidden={c.id === baseline.id}
                  >
                    {c.id !== baseline.id
                      ? delta(c.clogp, baseline.clogp)
                      : " "}
                  </small>
                </dd>
              </div>
              <div>
                <dt>Rotatable bonds</dt>
                <dd>
                  {displayNumber(c.rotors, 0)}
                  <small
                    className="property-delta"
                    aria-hidden={c.id === baseline.id}
                  >
                    {c.id !== baseline.id
                      ? delta(c.rotors, baseline.rotors, 0)
                      : " "}
                  </small>
                </dd>
              </div>
              <div>
                <dt>Ring drift</dt>
                <dd>{displayNumber(c.ringDriftA)} Å</dd>
              </div>
            </dl>
            <p className="comparison-note">
              {w.notes[c.id] || "No review note yet."}
            </p>
            <StudioLink
              className="text-link"
              to={`/experiments/${run.id}?candidate=${c.id}${c.structureId ? `&pose=${c.structureId}` : ""}`}
            >
              {c.structureId ? "Inspect this pose" : "Inspect this input"}
              <ArrowRight size={15} />
            </StudioLink>
            {c.structureId && (
              <details className="comparison-exact-state">
                <summary>Exact pose and prepared state</summary>
                <dl>
                  <div>
                    <dt>Pose</dt>
                    <dd>
                      <code>{c.structureId}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Prepared state</dt>
                    <dd>
                      <code>{c.preparedMoleculeId ?? "Unavailable"}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>SMILES</dt>
                    <dd>
                      <code>{c.smiles}</code>
                    </dd>
                  </div>
                </dl>
              </details>
            )}
          </article>
        ))}
      </div>
      {all.length === 1 && (
        <p className="field-help">
          Pin another candidate in the workspace to compare its properties with
          this baseline.
        </p>
      )}
      <p className="field-help">
        Scores are comparable only within the same preparation and protocol. A
        predicted contact or lower score alone is not evidence of improved
        binding.
      </p>
    </section>
  );
}
