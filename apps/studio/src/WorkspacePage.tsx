import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import {
  Camera,
  Download,
  Focus,
  Layers,
  LoaderCircle,
  Maximize2,
  Minimize2,
  Orbit,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import { CandidateTable } from "./CandidateTable";
import { ShortlistActions } from "./ShortlistActions";
import { EvidencePanel } from "./EvidencePanel";
import { useStudio, StudioLink, useStudioNavigate } from "./StudioContext";
import { useExperiment } from "./ExperimentLayout";
import { type Candidate, displayNumber } from "./data";
import {
  candidateExplanation,
  candidateStatus,
  defaultCandidate,
  duplicateOriginal,
} from "./candidateReview";
import { API_BASE, request, artifactUrl } from "./api";
import { normalizeCandidate } from "./useWorkspace";
import type { MolecularStructure } from "./molecularData";
import { EmptyState, InlineError } from "./ProductUI";
import { isActive } from "./experimentModel";
import type {
  MolecularViewportApi,
  ViewportFocus,
  ViewportLayers,
} from "./MolecularViewport";
const MolecularViewport = lazy(() => import("./MolecularViewport"));
export function selectedCandidate(
  base: Candidate,
  preferred?: string,
): Candidate {
  const pose = base.poses?.find(
    (p) => p.structureId === (preferred ?? base.structureId),
  );
  return pose
    ? {
        ...base,
        ...pose,
        id: base.id,
        depictionUrl:
          !base.recorded && pose.smiles
            ? `${API_BASE}/molecule/svg?smiles=${encodeURIComponent(pose.smiles)}&w=320&h=220`
            : base.depictionUrl,
      }
    : base;
}
export function WorkspacePage() {
  const run = useExperiment();
  return (
    <MolecularWorkspace
      experimentId={run.id}
      active={isActive(run)}
      runName={run.name}
    />
  );
}
export function MolecularWorkspace({
  reference = false,
  experimentId,
  active = false,
  runName,
}: {
  reference?: boolean;
  experimentId?: string;
  active?: boolean;
  runName?: string;
}) {
  const w = useStudio(),
    navigate = useStudioNavigate();
  const [params, setParams] = useSearchParams();
  const requested = params.get("candidate");
  const requestedPose = params.get("pose");
  const attemptId = params.get("attempt");
  const studyId = params.get("study");
  const [historical, setHistorical] = useState<{
    id: string;
    candidates: Candidate[];
    structures: MolecularStructure[];
  } | null>(null);
  const [attemptError, setAttemptError] = useState("");
  useEffect(() => {
    if (!attemptId || !experimentId) return;
    if (w.demo) {
      setAttemptError(
        "Historical attempt coordinates require the local API. Open the recorded current results instead.",
      );
      return;
    }
    let alive = true;
    setAttemptError("");
    Promise.all([
      request<{ items: Record<string, any>[] }>(
        `/experiments/${experimentId}/candidates?attempt_id=${encodeURIComponent(attemptId)}`,
      ),
      request<{ structures: MolecularStructure[] }>(
        `/experiments/${experimentId}/viewer?attempt_id=${encodeURIComponent(attemptId)}`,
      ),
    ])
      .then(([rows, view]) => {
        if (alive)
          setHistorical({
            id: attemptId,
            candidates: rows.items.map((c) =>
              normalizeCandidate(c, experimentId),
            ),
            structures: view.structures.map((s) => ({
              ...s,
              sdfUrl: artifactUrl(s.sdfUrl),
            })),
          });
      })
      .catch((e) => alive && setAttemptError(e.message));
    return () => {
      alive = false;
    };
  }, [attemptId, experimentId, w.demo]);
  const visibleStructures =
    attemptId && historical?.id === attemptId
      ? historical.structures
      : w.structures;
  const candidates =
    attemptId && historical?.id === attemptId
      ? historical.candidates
      : reference
        ? w.candidates.filter((c) => c.origin === "observed")
        : w.generated;
  const [mode, setMode] = useState<"references" | "generated" | "pinned">(
    reference ? "references" : "generated",
  );
  const base =
    candidates.find((c) => c.id === (requested ?? w.selectedId)) ??
    (!requested ? defaultCandidate(candidates) : undefined);
  const poseValid =
    !requestedPose || base?.poses?.some((p) => p.structureId === requestedPose);
  const candidate = base
    ? selectedCandidate(base, requestedPose ?? w.preferredPoses[base.id])
    : undefined;
  const reviewCandidates = candidates.map((c) =>
    selectedCandidate(
      c,
      c.id === base?.id
        ? (requestedPose ?? w.preferredPoses[c.id])
        : w.preferredPoses[c.id],
    ),
  );
  const original = candidate
    ? duplicateOriginal(candidate, candidates)
    : undefined;
  const inspectable = defaultCandidate(candidates.filter((c) => c.structureId));
  const structure = visibleStructures.find(
    (s) => s.id === candidate?.structureId,
  );
  const parent = visibleStructures.find(
    (s) => s.id === structure?.parentStructureId,
  );
  const [layers, setLayers] = useState<ViewportLayers>({
    pocket: true,
    contacts: true,
    core: true,
    parent: false,
  });
  const [focus, setFocus] = useState<ViewportFocus>({
    kind: "ligand",
    nonce: 0,
  });
  const [selectedResidue, setSelectedResidue] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [presentation, setPresentation] = useState<"list" | "table">("list");
  const [selectionLabel, setSelectionLabel] = useState("");
  const viewport = useRef<MolecularViewportApi | null>(null);
  const [viewportReady, setViewportReady] = useState(false);
  useEffect(() => {
    if (
      !attemptId &&
      candidate?.origin === "generated" &&
      candidate.structureId
    )
      w.ensurePose(candidate.structureId);
  }, [attemptId, candidate?.origin, candidate?.structureId, w.ensurePose]);
  useEffect(() => {
    const handle = (e: KeyboardEvent) => {
      if (
        (e.target as HTMLElement).matches("input,textarea,select") ||
        document.querySelector("dialog[open]")
      )
        return;
      if (e.key === "Escape") setExpanded(false);
      if (e.key === "/") {
        e.preventDefault();
        document
          .querySelector<HTMLInputElement>('[aria-label="Filter compounds"]')
          ?.focus();
      }
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, []);
  const choose = (id: string) => {
    setPresentation("list");
    w.setSelectedId(id);
    const next = new URLSearchParams(params);
    next.set("candidate", id);
    next.delete("pose");
    setParams(next, { replace: true });
    setSelectedResidue("");
  };
  const choosePose = async (id: string) => {
    if (!base) return;
    const ok = attemptId ? true : await w.preferPose(base.id, id);
    if (ok) {
      const next = new URLSearchParams(params);
      next.set("candidate", base.id);
      next.set("pose", id);
      setParams(next, { replace: true });
      setSelectedResidue("");
    }
  };
  const focusOn = (kind: "ligand" | "attachment" | "all") =>
    setFocus({ kind, nonce: Date.now() });
  const savePng = () => {
    const url = viewport.current?.capturePng();
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `capychem-${candidate?.name ?? "view"}.png`;
    document.body.append(a);
    a.click();
    a.remove();
  };
  if (attemptId && attemptError)
    return (
      <InlineError
        message={`This attempt could not be opened. ${attemptError}`}
      />
    );
  if (attemptId && (!historical || historical.id !== attemptId))
    return <div className="product-loading">Loading historical attempt…</div>;
  if (reference && w.loadError)
    return (
      <div className="workspace-selection-error">
        <InlineError message={w.loadError} onRetry={w.refreshReferences} />
      </div>
    );
  if (reference && !candidates.length)
    return (
      <div className="product-loading">
        <LoaderCircle className="spin" size={22} />
        Loading observed structures…
      </div>
    );
  if ((requested && !base) || !poseValid)
    return (
      <div className="workspace-selection-error">
        <InlineError
          message={
            !base
              ? "This candidate is not in the selected experiment."
              : "This pose does not belong to the selected candidate."
          }
        />
        <button
          className="secondary-button"
          onClick={() => {
            const next = new URLSearchParams(params);
            next.delete("candidate");
            next.delete("pose");
            setParams(next, { replace: true });
          }}
        >
          Show available candidates
        </button>
      </div>
    );
  const ready = reviewCandidates.filter(
    (c) => c.reviewReady || c.origin === "observed",
  ).length;
  const excluded = candidates.filter((c) =>
    ["outside_constraints", "invalid", "duplicate"].includes(c.status ?? ""),
  ).length;
  const hits = reviewCandidates.filter(
    (c) => c.asp86Contact && c.reviewReady,
  ).length;
  return (
    <div
      className={`molecular-workspace workspace-v5 workspace-presentation-${presentation} ${expanded ? "viewport-expanded" : ""}`}
    >
      {(attemptId || studyId) && (
        <div className="historical-attempt-notice">
          <span>{studyId ? "Study evidence · exact selected pose" : "Historical attempt · read-only evidence"}</span>
          {studyId && <StudioLink to={`/studies/${encodeURIComponent(studyId)}`}>Back to study</StudioLink>}
          <StudioLink to={`/experiments/${experimentId}`}>
            Return to current results
          </StudioLink>
        </div>
      )}
      <div className="workspace-outcomes">
        <span>
          {reference
            ? "Observed crystal structures"
            : `${ready} ready to inspect${excluded ? ` · ${excluded} excluded` : ""}${active ? " · calculation in progress" : " · current pose selections"}`}
        </span>
        {reference ? (
          <span>Each ligand is shown in its own observed receptor.</span>
        ) : candidates.length > 0 ? (
          <span className={hits ? "outcome-hit" : "outcome-neutral"}>
            {hits
              ? `${hits} with predicted Asp86 contact`
              : reviewCandidates.some((c) => c.asp86Contact)
                ? "No review-ready Asp86 contact"
                : reviewCandidates.some((c) => c.checks !== "unavailable")
                  ? "No predicted Asp86 contact"
                  : "Contact hypothesis not assessed"}
          </span>
        ) : (
          <StudioLink to={`/experiments/${experimentId}/activity`}>
            Follow calculation activity
          </StudioLink>
        )}
      </div>
      {!candidates.length ? (
        <EmptyState
          title={
            active ? "The experiment is running" : "No candidates are available"
          }
          body={
            active
              ? "Candidate outcomes will appear after preparation and evaluation. Follow the real stages in Activity."
              : "Open Activity for the recorded outcome and any errors, or create a new round with adjusted inputs."
          }
          action={
            <StudioLink
              className="primary-link"
              to={`/experiments/${experimentId}/activity`}
            >
              View activity
            </StudioLink>
          }
        />
      ) : (
        <>
          <nav className="workspace-jumps" aria-label="Workspace sections">
            <a href={`${location.pathname}${location.search}#workspace-candidates`}>Candidates</a>
            <a href={`${location.pathname}${location.search}#workspace-molecule`}>Molecular view</a>
            <a href={`${location.pathname}${location.search}#workspace-evidence`}>Evidence</a>
          </nav>
          <div className="molecular-review-grid">
            <div className="workspace-candidate-slot" id="workspace-candidates">
          <CandidateTable
            key={experimentId ?? "references"}
            presentation={presentation}
            onPresentationChange={setPresentation}
            candidates={reviewCandidates}
            selectedId={candidate?.id ?? ""}
            pinned={w.pins}
            onSelect={choose}
            onPin={(id) => void w.togglePin(id)}
            mode={mode}
            onMode={setMode}
            hasRun={!reference}
            demo={w.demo}
            runName={runName}
            readOnly={Boolean(attemptId)}
            sourceLabel={
              w.runs.find((r) => r.id === experimentId)?.config.source ===
              "libinvent"
                ? "LibInvent"
                : "Supplied candidate"
            }
            onNew={() => navigate("/experiments/new")}
          />
            </div>
            <section
              className="molecular-stage"
              id="workspace-molecule"
              aria-label="Molecular workspace"
            >
              <div className="stage-heading">
                <div>
                  <h2>{candidate?.name}</h2>
                  <p>
                    {candidate?.checks === "unavailable"
                      ? "Unevaluated input"
                      : candidate?.origin === "observed"
                        ? "Observed pose"
                        : candidate?.recorded
                          ? "Recorded prediction"
                          : "Computed pose"}{" "}
                    · {candidate?.receptorId ?? "CDK2"}
                  </p>
                  {base?.poses && base.poses.length > 1 && (
                    <select
                      className="pose-select"
                      aria-label="Displayed pose"
                      value={candidate?.structureId}
                      onChange={(e) => void choosePose(e.target.value)}
                    >
                      {[
                        ...new Set(
                          base.poses.map(
                            (p) =>
                              p.preparedMoleculeId ??
                              p.preparedStateId ??
                              "recorded",
                          ),
                        ),
                      ].map((state, i) => (
                        <optgroup
                          key={state}
                          label={`Prepared state ${i + 1} · ${state.slice(0, 8)}`}
                        >
                          {base
                            .poses!.filter(
                              (p) =>
                                (p.preparedMoleculeId ??
                                  p.preparedStateId ??
                                  "recorded") === state,
                            )
                            .map((p) => (
                              <option key={p.structureId} value={p.structureId}>
                                State {i + 1} · Pose{" "}
                                {base.poses!.indexOf(p) + 1} ·{" "}
                                {p.score === undefined
                                  ? "unscored"
                                  : `score ${displayNumber(p.score)}`}
                              </option>
                            ))}
                        </optgroup>
                      ))}
                    </select>
                  )}
                </div>
                <div className="stage-options">
                  <div className="stage-segment" aria-label="View mode">
                    <button
                      className={layers.pocket ? "active" : ""}
                      onClick={() => setLayers((l) => ({ ...l, pocket: true }))}
                    >
                      Pocket
                    </button>
                    <button
                      className={!layers.pocket ? "active" : ""}
                      onClick={() =>
                        setLayers((l) => ({ ...l, pocket: false }))
                      }
                    >
                      Ligand
                    </button>
                  </div>
                  <details className="stage-layers">
                    <summary aria-label="Molecular layers">
                      <Layers size={17} />
                    </summary>
                    <div>
                      {(
                        [
                          ["pocket", "Pocket context"],
                          ["parent", "Parent overlay"],
                          ["contacts", "Contacts"],
                          ["core", "Scaffold colors"],
                        ] as const
                      ).map(([key, label]) => (
                        <label key={key}>
                          <input
                            type="checkbox"
                            checked={layers[key]}
                            onChange={(e) =>
                              setLayers((l) => ({
                                ...l,
                                [key]: e.target.checked,
                              }))
                            }
                          />
                          {label}
                        </label>
                      ))}
                      <small>
                        Envelope shows pocket context, not binding strength.
                      </small>
                    </div>
                  </details>
                </div>
              </div>
              {candidate?.structureId && structure ? (
                <Suspense
                  fallback={
                    <div className="stage-loading">
                      <Orbit size={26} />
                      Preparing molecular view…
                    </div>
                  }
                >
                  <MolecularViewport
                    structures={visibleStructures}
                    structureId={candidate.structureId}
                    layers={layers}
                    focus={focus}
                    onReady={(api) => {
                      viewport.current = api;
                      setViewportReady(Boolean(api));
                    }}
                    onSelection={(s) => {
                      if (s.residueId) setSelectedResidue(s.residueId);
                      setSelectionLabel(s.label);
                    }}
                  />
                </Suspense>
              ) : (
                <div className="stage-loading">
                  {candidate?.structureId ? (
                    <LoaderCircle className="spin" size={26} />
                  ) : (
                    <TriangleAlert size={26} />
                  )}
                  <strong>
                    {candidate?.structureId
                      ? "Loading exact coordinates…"
                      : candidate
                        ? candidateStatus(candidate)
                        : "No evaluated pose"}
                  </strong>
                  <span>{candidate && candidateExplanation(candidate)}</span>
                  {!candidate?.structureId && original && (
                    <button
                      className="secondary-button"
                      onClick={() => choose(original.id)}
                    >
                      Open original · {original.name}
                    </button>
                  )}
                  {!candidate?.structureId && !original && inspectable && (
                    <button
                      className="secondary-button"
                      onClick={() => choose(inspectable.id)}
                    >
                      Inspect evaluated candidate · {inspectable.name}
                    </button>
                  )}
                  {candidate?.structureId &&
                    w.apiError.startsWith("Could not load this pose") && (
                      <button
                        className="secondary-button"
                        onClick={() => w.ensurePose(candidate.structureId!)}
                      >
                        Retry pose
                      </button>
                    )}
                </div>
              )}
              <div className="stage-bottom">
                <div className="stage-legend">
                  <span>
                    <i className="violet" />
                    Preserved scaffold
                  </span>
                  <span>
                    <i className="amber" />
                    {reference ||
                    w.runs.find((r) => r.id === experimentId)?.config
                      .protocol !== "guided_growth_cdk2_v2"
                      ? "N2 extension"
                      : "Para extension"}
                  </span>
                  {layers.parent && parent && (
                    <span>
                      <i className="ghost" />
                      {parent.origin === "template"
                        ? "Transferred parent template"
                        : "Observed parent"}
                    </span>
                  )}
                </div>
                <div className="stage-tools">
                  <button
                    aria-label="Focus ligand"
                    title="Focus ligand"
                    onClick={() => focusOn("ligand")}
                  >
                    <Focus size={17} />
                  </button>
                  <button
                    aria-label="Reset camera"
                    title="Reset camera"
                    onClick={() => viewport.current?.resetCamera()}
                  >
                    <RotateCcw size={16} />
                  </button>
                  <button
                    aria-label="Capture molecular view"
                    title="Download view as PNG"
                    disabled={!viewportReady}
                    onClick={savePng}
                  >
                    <Camera size={16} />
                  </button>
                  {structure?.sdfUrl && (
                    <a
                      href={structure.sdfUrl}
                      download
                      aria-label="Download selected pose"
                      title="Download exact selected pose SDF"
                    >
                      <Download size={16} />
                    </a>
                  )}
                  <button
                    aria-label={
                      expanded ? "Exit expanded view" : "Expand molecular view"
                    }
                    title="Expand view"
                    onClick={() => setExpanded((v) => !v)}
                  >
                    {expanded ? (
                      <Minimize2 size={17} />
                    ) : (
                      <Maximize2 size={17} />
                    )}
                  </button>
                </div>
              </div>
              <span className="sr-only" role="status">
                {selectionLabel}
              </span>
            </section>
            <div className="workspace-evidence-slot" id="workspace-evidence">
            {candidate && (
              <EvidencePanel
                candidate={candidate}
                structure={structure}
                pinned={w.pins.includes(candidate.id)}
                onPin={() => void w.togglePin(candidate.id)}
                selectedResidue={selectedResidue}
                onFocus={(residueId) => {
                  setSelectedResidue(residueId);
                  setFocus({ kind: "residue", residueId, nonce: Date.now() });
                }}
                note={w.notes[candidate.id] ?? ""}
                onNote={(t) => w.setNote(candidate.id, t)}
                onSaveNote={() => void w.saveNote(candidate.id)}
                noteSaving={w.noteSaving}
                noteSaved={
                  (w.notes[candidate.id] ?? "") ===
                  (w.savedNotes[candidate.id] ?? "")
                }
                demo={w.demo}
                readOnly={Boolean(attemptId)}
              />
            )}
            </div>
          </div>
          {!reference && !attemptId && !active && experimentId && <ShortlistActions experimentId={experimentId} candidates={reviewCandidates}/>}
        </>
      )}
    </div>
  );
}
