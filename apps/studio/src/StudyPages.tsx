import { useState } from "react";
import { useParams } from "react-router";
import { Button } from "@astryxdesign/core/Button";
import {
  ArrowDownToLine,
  ArrowRight,
  Layers,
  Plus,
  Square,
} from "lucide-react";
import {
  StudioLink,
  useStudio,
  useStudioNavigate,
  protocolLabel,
} from "./StudioContext";
import {
  EmptyState,
  InlineError,
  LoadingState,
  PageHeader,
  StatusLabel,
  readableDate,
} from "./ProductUI";
import { request } from "./api";
import { download } from "./data";
import { fromSpec } from "./useWorkspace";
import { CollectionTabs, CollectionToolbar } from "./CollectionToolbar";
import { StudioActionLink } from "./StudioActionLink";
import { useStudies } from "./useStudies";
import {
  studyActive,
  saveStudyDraft,
  type Study,
  type StudyObservation,
} from "./studyModel";
import "./study.css";

export function WorkTabs({
  selected,
}: {
  selected: "experiments" | "studies";
}) {
  return <CollectionTabs selected={selected} />;
}
export function StudyIndexPage() {
  const w = useStudio(),
    state = useStudies(w.demo);
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all");
  const items = state.items.filter(
    (s) =>
      s.label.toLowerCase().includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "active" ? studyActive(s) : s.status === filter)),
  );
  return (
    <section className="product-page study-index flow-v5 collection-page">
      <PageHeader
        title="Studies"
        description="Compare one molecular series across repeated sampling runs."
        actions={
          <StudioActionLink to="/studies/new" label="New study" variant="primary" icon={<Plus size={16} />} />
        }
      />
      <WorkTabs selected="studies" />
      <CollectionToolbar label="Search studies" placeholder="Find a study…" query={query} onQuery={setQuery}>
        <select
          aria-label="Filter study status"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All statuses</option>
          <option value="active">In progress</option>
          <option value="completed">Completed</option>
          <option value="completed_with_errors">Partial results</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </CollectionToolbar>
      <p className="flow-collection-context">One molecular series, repeated across declared sampling seeds.</p>
      {state.error && (
        <InlineError message={state.error} onRetry={state.refresh} />
      )}
      {state.loading ? (
        <LoadingState label="Loading studies…" />
      ) : items.length ? (
        <div className="product-table-wrap">
          <table className="product-table study-index-table">
            <thead>
              <tr>
                <th>Study</th>
                <th>Status</th>
                <th>Inputs</th>
                <th>Runs finished</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  <td>
                    <StudioLink to={`/studies/${s.id}`}>
                      {s.label}
                      <ArrowRight size={14} />
                    </StudioLink>
                    <small>{protocolLabel(s.base_spec.protocol)}</small>
                  </td>
                  <td>
                    <StatusLabel status={s.status} />
                  </td>
                  <td>
                    {s.base_spec.candidate_source?.candidates?.length ?? "—"}
                  </td>
                  <td>
                    {s.counts.finished ?? 0} / {s.seed_pairs.length}
                  </td>
                  <td>{readableDate(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        !state.error && (
          <EmptyState
            icon={<Layers size={26} />}
            title={
              query || filter !== "all"
                ? "No matching studies"
                : "See what holds across runs"
            }
            body={
              query || filter !== "all"
                ? "Try another search or status filter."
                : w.demo
                  ? "This recorded bundle does not contain a study. Run CapyChem locally to compare a series across seeds."
                  : "Use the same molecules and rules with different sampling seeds, then inspect the evidence behind each result."
            }
            action={
              <StudioActionLink to="/studies/new" label="Plan a study" variant="primary" endContent={<ArrowRight size={16} />} />
            }
          />
        )
      )}
      {state.hasMore && (
        <div className="study-history-more">
          <Button
            label={state.loadingMore ? "Loading…" : "Load more studies"}
            variant="secondary"
            isDisabled={state.loadingMore}
            onClick={state.loadMore}
          />
        </div>
      )}
    </section>
  );
}

export function observationLabel(o?: StudyObservation): string {
  if (!o) return "Not assessed";
  if (o.selected_pose_id)
    return o.review_ready
      ? o.asp86_contact
        ? "Contact + ready"
        : "Ready · no contact"
      : "Outside brief";
  if (o.status === "duplicate") return "Duplicate";
  if (o.status === "invalid") return "Invalid input";
  if (o.status === "outside_constraints") return "Excluded";
  if (o.status === "deferred_budget") return "Budget deferred";
  if (o.error || ["evaluation_error", "no_pose"].includes(o.status))
    return "Evaluation error";
  if (["failed", "cancelled"].includes(o.experiment_status))
    return o.experiment_status === "failed" ? "Run failed" : "Cancelled";
  if (o.experiment_status === "queued") return "Queued";
  if (o.experiment_status === "running") return "In progress";
  return "Not assessed";
}
export function observationPath(
  o: StudyObservation,
  studyId?: string,
  includeAttempt = true,
) {
  if (!o.candidate_id) return `/experiments/${o.experiment_id}/activity`;
  const params = new URLSearchParams({ candidate: o.candidate_id });
  if (o.selected_pose_id) params.set("pose", o.selected_pose_id);
  if (o.attempt_id && includeAttempt) params.set("attempt", o.attempt_id);
  if (studyId) params.set("study", studyId);
  return `/experiments/${o.experiment_id}?${params}`;
}
function scoreRange(observations: StudyObservation[]) {
  const values = observations.flatMap((o) =>
    typeof o.score === "number" && Number.isFinite(o.score) ? [o.score] : [],
  );
  if (!values.length) return "—";
  const low = Math.min(...values),
    high = Math.max(...values);
  return low.toFixed(2) === high.toFixed(2)
    ? low.toFixed(2)
    : `${low.toFixed(2)} to ${high.toFixed(2)}`;
}
function contactAtoms(observation: StudyObservation) {
  if (!observation.asp86_contacts?.length) return "";
  const atoms = [
    ...new Set(observation.asp86_contacts.map((c) => c.protein_atom_name)),
  ].sort();
  return `Asp86 ${atoms.join(" + ")}`;
}
function hasOHWarning(observation: StudyObservation) {
  return observation.hydrogen_preparation?.warnings.some(
    (warning) => warning.code === "oh_orientation_not_sampled",
  );
}
export function StudyPage() {
  const { studyId } = useParams();
  const w = useStudio(),
    navigate = useStudioNavigate();
  const state = useStudies(w.demo, studyId);
  const [tab, setTab] = useState<"results" | "runs">("results"),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all");
  const [actionError, setActionError] = useState(""),
    [busy, setBusy] = useState("");
  if (state.loading) return <LoadingState label="Loading study evidence…" />;
  if (!state.study)
    return (
      <section className="product-page">
        <PageHeader
          title={state.missing ? "Study not found" : "Study unavailable"}
        />
        {state.error && (
          <InlineError message={state.error} onRetry={state.refresh} />
        )}
        <StudioLink className="text-link" to="/studies">
          Back to studies <ArrowRight size={16} />
        </StudioLink>
      </section>
    );
  const s = state.study;
  const inputs = s.candidates ?? [];
  const visible = inputs.filter(
    (c) =>
      c.name.toLowerCase().includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "contact"
          ? c.contact_hit_runs > 0
          : filter === "incomplete"
            ? c.observed_runs < c.planned_runs
            : c.observed_runs > 0 && c.contact_hit_runs === 0)),
  );
  const newStudy = () => {
    saveStudyDraft(w.demo, {
      config: {
        ...fromSpec(s.base_spec, `${s.label} · next study`.slice(0, 160)),
        source: "supplied",
      },
      seeds: s.seed_pairs.map((pair) => ({ ...pair })),
      step: 0,
    });
    navigate("/studies/new");
  };
  const exportStudy = async () => {
    setActionError("");
    setBusy("export");
    try {
      const record = w.demo
        ? s.export_url
          ? await fetch(s.export_url).then((r) => {
              if (!r.ok)
                throw new Error("The recorded study export is unavailable.");
              return r.json();
            })
          : { kind: "recorded_study", study: s }
        : await request<unknown>(`/studies/${s.id}/export`);
      download(`capychem-study-${s.id}.json`, JSON.stringify(record, null, 2));
    } catch (e) {
      setActionError(
        e instanceof Error ? e.message : "The study could not be exported.",
      );
    } finally {
      setBusy("");
    }
  };
  const cancel = async () => {
    setActionError("");
    setBusy("cancel");
    try {
      await request(`/studies/${s.id}/cancel`, { method: "POST" });
      state.refresh();
    } catch (e) {
      setActionError(
        e instanceof Error ? e.message : "Cancellation could not be requested.",
      );
    } finally {
      setBusy("");
    }
  };
  return (
    <section className="product-page study-page flow-v5">
      <nav className="study-breadcrumb" aria-label="Breadcrumb">
        <StudioLink to="/experiments">Experiments</StudioLink>
        <span>/</span>
        <StudioLink to="/studies">Studies</StudioLink>
      </nav>
      <PageHeader
        title={s.label}
        actions={
          <>
            <Button
              label={busy === "export" ? "Exporting…" : "Export study"}
              variant="secondary"
              icon={<ArrowDownToLine size={16} />}
              isDisabled={!!busy}
              onClick={() => void exportStudy()}
            />
            <Button label="New study" variant="primary" icon={<Plus size={16} />} onClick={newStudy} />
          </>
        }
      />
      <div className="study-meta">
        <StatusLabel status={s.status} />
        <span>
          {s.counts.finished ?? 0} / {s.seed_pairs.length} runs finished
        </span>
        <span>
          {w.presets.find((p) => p.id === s.base_spec.target_preparation_id)
            ?.name || s.base_spec.target_preparation_id}
        </span>
        {w.demo && <span>Recorded example</span>}
      </div>
      {(state.error || actionError) && (
        <InlineError
          message={actionError || state.error}
          onRetry={state.error ? state.refresh : undefined}
        />
      )}
      <p className="study-purpose">
        Repeat the same candidates with different sampling seeds.
      </p>
      <dl className="study-summary">
        <div>
          <dt>Candidates</dt>
          <dd>
            {s.base_spec.candidate_source?.candidates?.length ?? inputs.length}
          </dd>
        </div>
        <div>
          <dt>Replicates</dt>
          <dd>{s.seed_pairs.length}</dd>
        </div>
        <div>
          <dt>Protocol</dt>
          <dd>{protocolLabel(s.base_spec.protocol)}</dd>
        </div>
      </dl>
      <div
        className="study-tabs"
        role="tablist"
        aria-label="Study views"
        onKeyDown={(e) => {
          if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
            e.preventDefault();
            const next =
              e.key === "Home"
                ? "results"
                : e.key === "End"
                  ? "runs"
                  : tab === "results"
                    ? "runs"
                    : "results";
            setTab(next);
            document.getElementById(`study-${next}-tab`)?.focus();
          }
        }}
      >
        <button
          role="tab"
          id="study-results-tab"
          tabIndex={tab === "results" ? 0 : -1}
          aria-selected={tab === "results"}
          aria-controls="study-results"
          onClick={() => setTab("results")}
        >
          Results
        </button>
        <button
          role="tab"
          id="study-runs-tab"
          tabIndex={tab === "runs" ? 0 : -1}
          aria-selected={tab === "runs"}
          aria-controls="study-runs"
          onClick={() => setTab("runs")}
        >
          Run details
        </button>
      </div>
      {tab === "results" ? (
        <section
          role="tabpanel"
          id="study-results"
          aria-labelledby="study-results-tab"
        >
          <div className="section-heading">
            <div>
              <h2>Evidence across runs</h2>
              <p className="section-description">
                Counts describe protocol-selected poses. Open a cell to inspect
                its exact evidence.
              </p>
            </div>
          </div>
          <CollectionToolbar label="Search study candidates" placeholder="Find a compound…" query={query} onQuery={setQuery}>
            <select
              aria-label="Filter study candidates"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">All candidates</option>
              <option value="contact">Contact in any run</option>
              <option value="no_contact">Assessed, no eligible contact</option>
              <option value="incomplete">Incomplete assessment</option>
            </select>
          </CollectionToolbar>
          <p className="study-scroll-hint">
            Scroll the table to compare all seed runs.
          </p>
          {inputs.some((c) => c.observations.some((o) => o.unspecified_stereochemistry)) && (
            <p className="study-preparation-note" role="note" aria-label="Study stereochemistry warning">
              Some inputs leave stereochemistry unspecified. Different runs may
              prepare different stereoisomers, so their contact counts do not
              represent repeated evaluation of one fully specified molecule.
              Open each result to inspect its prepared state.
            </p>
          )}
          <div
            className="study-matrix-scroll"
            tabIndex={0}
            role="region"
            aria-label="Candidate evidence across sampling seeds"
          >
            <table className="study-matrix">
              <thead>
                <tr>
                  <th scope="col">Candidate</th>
                  {s.seed_pairs.map((seed, i) => (
                    <th key={i} scope="col">
                      Vina seed {seed.vina}
                      <small>Embedding {seed.embedding}</small>
                    </th>
                  ))}
                  <th scope="col">Ready</th>
                  <th scope="col">Asp86 + ready</th>
                  <th scope="col">
                    Vina range<small>kcal/mol</small>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => (
                  <tr key={c.candidate_index}>
                    <th scope="row">
                      <strong>{c.name}</strong>
                      <small>
                        {c.observed_runs} / {c.planned_runs} assessed
                      </small>
                      {c.observations.some(hasOHWarning) && (
                        <small className="study-preparation-flag">
                          O–H orientation not sampled
                        </small>
                      )}
                      {c.observations.some((o) => o.unspecified_stereochemistry) && (
                        <small className="study-preparation-flag">
                          Stereochemistry unspecified · inspect each prepared state
                        </small>
                      )}
                    </th>
                    {s.seed_pairs.map((_, i) => {
                      const observation = c.observations.find(
                          (o) => o.run_ordinal === i,
                        ),
                        label = observationLabel(observation);
                      return (
                        <td key={i}>
                          {observation ? (
                            <StudioLink
                              className={`study-result-cell ${observation.review_ready ? (observation.asp86_contact ? "contact" : "ready") : "unassessed"}`}
                              to={observationPath(observation, s.id, !w.demo)}
                              aria-label={`${c.name}, run ${i + 1}: ${label}. Inspect evidence`}
                            >
                              <span>{label}</span>
                              {contactAtoms(observation) && (
                                <small>{contactAtoms(observation)}</small>
                              )}
                              {typeof observation.score === "number" && (
                                <small>
                                  {observation.score.toFixed(2)} kcal/mol
                                </small>
                              )}
                              {observation.error && (
                                <small>See error details</small>
                              )}
                              <ArrowRight size={13} />
                            </StudioLink>
                          ) : (
                            <span className="field-help">Not assessed</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="study-count">
                      {c.review_ready_runs} / {c.planned_runs}
                    </td>
                    <td className="study-count">
                      {c.contact_hit_runs} / {c.planned_runs}
                    </td>
                    <td className="study-range">
                      {scoreRange(c.observations)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!visible.length && (
            <EmptyState
              title="No matching candidates"
              body="Try another search or evidence filter."
            />
          )}
          <p className="study-interpretation">
            Unassessed, excluded and failed inputs are distinct from a pose with
            no detected contact. Asp86 N is a backbone atom; OD1 and OD2 belong
            to its side chain. The same contact count can describe different
            interactions. Counts across seeds are not binding probabilities. A
            lower Vina score alone does not establish stronger binding.
          </p>
          {inputs.some((c) => c.observations.some(hasOHWarning)) && (
            <p className="study-preparation-note">
              Some inputs contain an O–H group whose hydrogen orientation was
              not sampled. Their donor contacts may depend on that preparation
              choice. Open the pose’s Calculation details for the saved
              preparation record; this flag does not measure sensitivity.
            </p>
          )}
        </section>
      ) : (
        <section
          role="tabpanel"
          id="study-runs"
          aria-labelledby="study-runs-tab"
        >
          <h2>Run details</h2>
          <p className="section-description">
            Each member keeps its own attempt history, inputs and artifacts.
          </p>
          <div className="study-run-list">
            {s.members.map((m) => (
              <article key={m.experiment.id}>
                <div>
                  <h3>Run {m.ordinal + 1}</h3>
                  <p>
                    Embedding {m.seeds.embedding} · Vina {m.seeds.vina}
                  </p>
                </div>
                <StatusLabel status={m.experiment.status} />
                <StudioLink
                  className="text-link"
                  to={`/experiments/${m.experiment.id}/activity`}
                >
                  Open activity <ArrowRight size={15} />
                </StudioLink>
                <StudioLink
                  className="text-link"
                  to={`/experiments/${m.experiment.id}`}
                >
                  Open workspace <ArrowRight size={15} />
                </StudioLink>
                {m.experiment.error && (
                  <p className="study-run-error">{m.experiment.error}</p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
      <details className="study-disclosure">
        <summary>Frozen study settings</summary>
        <dl className="study-exact">
          <div>
            <dt>Study identity</dt>
            <dd>
              <code>{s.id}</code>
            </dd>
          </div>
          <div>
            <dt>Specification hash</dt>
            <dd>
              <code>{s.spec_hash}</code>
            </dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{readableDate(s.created_at)}</dd>
          </div>
        </dl>
        <pre>
          {JSON.stringify(
            { base_spec: s.base_spec, seed_pairs: s.seed_pairs },
            null,
            2,
          )}
        </pre>
      </details>
      {studyActive(s) && (
        <div className="study-progress-footer">
          <span role="status">
            {s.status === "queued"
              ? "Waiting for the local worker"
              : "Calculation in progress"}{" "}
            · {s.counts.finished ?? 0} of {s.seed_pairs.length} finished
          </span>
          {!w.demo && (
            <Button
              label={busy === "cancel" ? "Requesting…" : "Cancel unfinished runs"}
              variant="secondary"
              icon={<Square size={13} />}
              isDisabled={!!busy}
              onClick={() => void cancel()}
            />
          )}
        </div>
      )}
    </section>
  );
}
