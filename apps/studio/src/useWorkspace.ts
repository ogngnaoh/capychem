import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { loadMolecularDataset, type MolecularStructure } from "./molecularData";
import { type Candidate, referenceCandidate } from "./data";
import {
  DEFAULT_EXPERIMENT,
  candidateOrigins,
  parseCandidates,
  type ExperimentConfig,
} from "./experimentConfig";
import { isActive, type ExperimentRun } from "./experimentModel";
import { request, artifactUrl, API_BASE, ApiError } from "./api";
import { loadRecordedManifest, type RecordedExperiment } from "./recordedData";
import { defaultCandidate } from "./candidateReview";

export const DEMO = new URLSearchParams(location.search).get("mode") === "demo";
const UI_STORE = `capychem-studio-ui-v2-${DEMO ? "demo" : "live"}`;
type UiState = {
  selectedRun?: string;
  selectedId?: string;
  pins: string[];
  notes: Record<string, string>;
  drafts?: Record<string, string>;
  preferredPoses?: Record<string, string>;
};
function restore(): UiState {
  try {
    const saved = JSON.parse(localStorage.getItem(UI_STORE) || "null");
    if (
      saved &&
      Array.isArray(saved.pins) &&
      saved.pins.every((id: unknown) => typeof id === "string") &&
      saved.notes &&
      typeof saved.notes === "object" &&
      !Array.isArray(saved.notes) &&
      Object.values(saved.notes).every((note) => typeof note === "string") &&
      (saved.selectedRun === undefined ||
        typeof saved.selectedRun === "string") &&
      (saved.selectedId === undefined ||
        typeof saved.selectedId === "string") &&
      (saved.preferredPoses === undefined ||
        (saved.preferredPoses &&
          typeof saved.preferredPoses === "object" &&
          !Array.isArray(saved.preferredPoses) &&
          Object.values(saved.preferredPoses).every(
            (value) => typeof value === "string",
          ))) &&
      (saved.drafts === undefined ||
        (saved.drafts &&
          typeof saved.drafts === "object" &&
          !Array.isArray(saved.drafts) &&
          Object.values(saved.drafts).every(
            (note) => typeof note === "string",
          )))
    )
      return saved;
  } catch {
    /* storage may be unavailable */
  }
  return { pins: [], notes: {} };
}
export type Health = {
  loading: boolean;
  connected: boolean;
  ready: boolean;
  generatorReady: boolean;
  workerReady: boolean;
  detail: string;
  raw?: unknown;
};
type Decision = {
  pinned: boolean;
  notes: string;
  preferred_pose_id: string | null;
  revision: number;
};
type DecisionChange = Partial<Omit<Decision, "revision">>;
const SUBMISSION_STORE = "capychem-pending-submissions-v1";
const submissionKeys = new Map<string, string>();
try {
  const saved = JSON.parse(sessionStorage.getItem(SUBMISSION_STORE) || "[]");
  if (Array.isArray(saved))
    for (const entry of saved.slice(-8))
      if (
        Array.isArray(entry) &&
        typeof entry[0] === "string" &&
        typeof entry[1] === "string"
      )
        submissionKeys.set(entry[0], entry[1]);
} catch {
  /* In-memory retry protection still works if storage is unavailable. */
}
function persistSubmissionKeys() {
  try {
    sessionStorage.setItem(
      SUBMISSION_STORE,
      JSON.stringify([...submissionKeys].slice(-8)),
    );
  } catch {
    /* Storage is optional. */
  }
}
function submissionKey(payload: string) {
  const existing = submissionKeys.get(payload);
  if (existing) return existing;
  const key = crypto.randomUUID();
  submissionKeys.set(payload, key);
  persistSubmissionKeys();
  return key;
}
function clearSubmissionKey(payload: string) {
  submissionKeys.delete(payload);
  persistSubmissionKeys();
}
type RawRecord = Record<string, any>;
function listOf(value: any, key: string): any[] {
  return Array.isArray(value)
    ? value
    : Array.isArray(value?.[key])
      ? value[key]
      : Array.isArray(value?.items)
        ? value.items
        : [];
}
export function fromSpec(
  spec: RawRecord = {},
  name = "CDK2 exploration",
): ExperimentConfig {
  const source = spec.candidate_source ?? {};
  return {
    ...DEFAULT_EXPERIMENT,
    name,
    source: source.kind === "libinvent" ? "libinvent" : "supplied",
    count: source.raw_proposal_count ?? 32,
    seed: source.seed ?? 43,
    maxCandidates: spec.limits?.max_unique_candidates_evaluated ?? 24,
    conformers: spec.limits?.embedding_attempts_per_candidate ?? 8,
    maxLogP: spec.constraints?.max_clogp ?? 4.5,
    maxMolecularWeight: spec.constraints?.max_molecular_weight ?? 450,
    maxRotatableBonds: spec.constraints?.max_rotatable_bonds ?? 8,
    evaluationSeconds: spec.limits?.evaluation_admission_seconds ?? 600,
    embeddingSeed: spec.seeds?.embedding,
    vinaSeed: spec.seeds?.vina,
    protocol: spec.protocol,
    targetPreparationId: spec.target_preparation_id,
    parentId: spec.parent_experiment_id,
    originCandidates: Array.isArray(spec.candidate_origins)
      ? spec.candidate_origins.flatMap((origin: RawRecord) => {
          const entry = source.candidates?.[origin.candidate_index];
          return entry ? [{ name: entry.name, smiles: entry.smiles,
            origin: { experiment_id: origin.experiment_id, candidate_id: origin.candidate_id,
              ...(origin.pose_id ? { pose_id: origin.pose_id } : {}) } }] : [];
        })
      : undefined,
    suppliedText:
      source.candidates
        ?.map((c: RawRecord) => `${c.smiles} ${c.name}`)
        .join("\n") ?? DEFAULT_EXPERIMENT.suppliedText,
  };
}
export function toRequest(config: ExperimentConfig) {
  return {
    schema_version: 1,
    label: config.name,
    target_preparation_id: config.targetPreparationId ?? "cdk2_1h1p",
    protocol: config.protocol ?? "guided_local_cdk2_v1",
    candidate_source:
      config.source === "libinvent"
        ? {
            kind: "libinvent",
            raw_proposal_count: config.count,
            seed: config.seed,
          }
        : {
            kind: "supplied",
            candidates: parseCandidates(config.suppliedText),
          },
    limits: {
      max_unique_candidates_evaluated: config.maxCandidates,
      embedding_attempts_per_candidate: config.conformers,
      evaluation_admission_seconds: config.evaluationSeconds ?? 600,
    },
    constraints: {
      max_molecular_weight: config.maxMolecularWeight ?? 450,
      max_clogp: config.maxLogP,
      max_rotatable_bonds: config.maxRotatableBonds ?? 8,
      formal_charge: 0,
    },
    ...(config.embeddingSeed !== undefined || config.vinaSeed !== undefined
      ? {
          seeds: {
            ...(config.embeddingSeed !== undefined
              ? { embedding: config.embeddingSeed }
              : {}),
            ...(config.vinaSeed !== undefined ? { vina: config.vinaSeed } : {}),
          },
        }
      : {}),
    ...(config.parentId ? { parent_experiment_id: config.parentId } : {}),
    ...(config.source === "supplied" && candidateOrigins(config).length
      ? { candidate_origins: candidateOrigins(config) } : {}),
  };
}
function normalizeStage(stage: string): string {
  if (/failed|cancelled|interrupted/.test(stage)) return "stopped";
  if (/prepar|baseline|queued/.test(stage)) return "prepare";
  if (/generat|propos|filter|screen/.test(stage)) return "generate";
  if (/complet|review|final/.test(stage)) return "review";
  return "evaluate";
}
export function normalizeRun(raw: RawRecord): ExperimentRun {
  const spec = raw.spec?.request ?? raw.spec ?? raw.request ?? {};
  const counts = raw.counts ?? {};
  const started = raw.started_at
    ? new Date(raw.started_at).getTime()
    : undefined;
  const end = raw.finished_at
    ? new Date(raw.finished_at).getTime()
    : Date.now();
  return {
    id: raw.id,
    name: raw.label ?? raw.name ?? "Untitled experiment",
    createdAt: raw.created_at,
    status: raw.status,
    latestSequence: raw.latest_sequence,
    stage: normalizeStage(raw.stage ?? "queued"),
    candidateCount:
      counts.proposals ??
      counts.candidates ??
      counts.unique_candidates ??
      counts.unique ??
      counts.total ??
      raw.candidate_count ??
      0,
    config: fromSpec(spec, raw.label),
    parentId: raw.parent_experiment_id,
    elapsedSeconds: started ? (end - started) / 1000 : undefined,
    message:
      raw.error ??
      raw.message ??
      (raw.cancel_requested &&
      (raw.status === "queued" || raw.status === "running")
        ? "Cancellation requested. Finishing the current safe checkpoint."
        : undefined),
    completedCandidates: counts.evaluated_candidates ?? counts.evaluated,
    totalCandidates:
      counts.evaluation_total ??
      counts.scheduled_candidates ??
      (counts.proposals
        ? Math.min(
            spec.limits?.max_unique_candidates_evaluated ?? 24,
            counts.proposals - (counts.excluded ?? 0),
          )
        : undefined),
    objectiveHits:
      raw.outcome?.objective_hits ??
      raw.outcome?.asp86_hits ??
      counts.asp86_hits ??
      counts.review_ready_with_asp86,
    errorCount:
      (counts.pose_errors ?? counts.pose_failures ?? 0) +
      (counts.embedding_errors ?? 0),
    poseFailureCount: counts.pose_errors ?? counts.pose_failures ?? 0,
    embeddingFailureCount: counts.embedding_errors ?? 0,
    spec: raw.spec,
  };
}
export function normalizeCandidate(
  raw: RawRecord,
  experimentId: string,
): Candidate {
  if (raw.origin === "generated" && "mw" in raw) {
    const number = (v: any) =>
      typeof v === "number" && Number.isFinite(v) ? v : undefined;
    return {
      ...raw,
      id: raw.id,
      experimentId,
      mw: number(raw.mw) ?? NaN,
      clogp: number(raw.clogp) ?? NaN,
      rotors: number(raw.rotors) ?? NaN,
      charge: number(raw.formalCharge ?? raw.charge),
      score: number(raw.score),
      ringDriftA: number(raw.ringDriftA),
      asp86Contact: raw.asp86Contact ?? undefined,
      smiles: raw.smiles ?? "",
      failures: raw.failures ?? [],
      embeddingErrors: raw.embeddingErrors ?? [],
      depictionUrl:
        raw.depictionUrl ??
        (raw.status === "invalid"
          ? undefined
          : `${API_BASE}/molecule/svg?smiles=${encodeURIComponent(raw.smiles)}&w=320&h=220`),
      poses: (raw.poses ?? []).map((p: RawRecord) => ({
        ...p,
        failures: p.failures ?? p.evidence?.geometry_failures ?? [],
        score: number(p.score),
        ringDriftA: number(p.ringDriftA),
        sdfUrl: artifactUrl(p.sdfUrl),
      })),
    } as Candidate;
  }
  const record = raw.record ?? raw;
  const properties = record.properties ?? {};
  const selected = raw.selected_pose ?? record.selected_pose;
  const evaluation =
    selected?.evaluation ?? selected?.evidence ?? selected ?? {};
  const poses = (raw.poses ?? record.poses ?? []).map((p: RawRecord) => {
    const e = p.evaluation ?? p.evidence ?? p;
    return {
      structureId: p.id,
      label: p.label ?? p.source_id ?? p.id,
      score: e.vina_score ?? e.score,
      checks:
        e.geometry_pass === undefined
          ? "unavailable"
          : e.geometry_pass
            ? "pass"
            : "fail",
      contacts: e.contact_details?.length ?? e.contacts?.length ?? 0,
      ringDriftA: e.purine_ring_drift_A ?? e.ring_drift_A,
      reviewReady: Boolean(e.review_ready),
      asp86Contact: e.asp86_hbond ?? e.asp86_contact,
      smiles: p.prepared_smiles ?? p.smiles,
      sdfUrl: artifactUrl(p.sdf_url),
      preparedStateId: p.prepared_molecule_id,
      failures: e.geometry_failures ?? [],
    };
  });
  const selectedId = raw.selected_pose_id ?? selected?.id;
  const selectedPose = poses.find(
    (p: RawRecord) => p.structureId === selectedId,
  );
  return {
    id: raw.id,
    name: raw.name ?? record.name ?? raw.source_id,
    description:
      raw.status === "outside_constraints"
        ? "Outside design profile"
        : raw.status === "deferred_budget"
          ? "Evaluation budget reached"
          : raw.status === "duplicate"
            ? "Duplicate proposal"
            : raw.status === "invalid"
              ? "Invalid input"
              : "N2 exploration",
    origin: "generated",
    structureId: selectedId,
    selectedPoseId: selectedId,
    receptorId: raw.receptorId ?? raw.receptor_id ?? "Unspecified receptor",
    smiles:
      record.prepared_smiles ??
      raw.canonical_smiles ??
      raw.proposal_smiles ??
      record.smiles ??
      "",
    proposalSmiles: raw.proposal_smiles ?? record.smiles,
    mw: properties.molecular_weight ?? NaN,
    clogp: properties.clogp ?? NaN,
    rotors: properties.rotatable_bonds ?? NaN,
    charge: properties.formal_charge,
    contacts:
      evaluation.contact_details?.length ?? evaluation.contacts?.length ?? 0,
    checks:
      evaluation.geometry_pass === undefined
        ? "unavailable"
        : evaluation.geometry_pass
          ? "pass"
          : "fail",
    failures: record.filter_failures ?? record.failures ?? [],
    sourceId: raw.source_id ?? record.id,
    duplicateOfSourceId: record.duplicate_of,
    error: record.error,
    score: evaluation.vina_score,
    poseCount: poses.length || record.poses?.length || 0,
    ringDriftA: evaluation.purine_ring_drift_A,
    reviewReady: Boolean(evaluation.review_ready),
    status: raw.status ?? record.status,
    selectionPolicy: record.selection_policy,
    asp86Contact: evaluation.asp86_hbond,
    stereochemistryNote: record.stereochemistry_note,
    partial: Boolean(record.pose_errors?.length),
    poseErrors: record.pose_errors,
    embeddingErrors: record.embedding_errors ?? [],
    poses,
    depictionUrl: artifactUrl(raw.depiction_url),
    experimentId,
    ...selectedPose,
  };
}

export function useWorkspace() {
  const [recordedExperiments, setRecordedExperiments] = useState<
    RecordedExperiment[]
  >([]);
  const [referenceRetry, setReferenceRetry] = useState(0);
  const [saved] = useState(restore);
  const [referenceStructures, setReferenceStructures] = useState<
    MolecularStructure[]
  >([]);
  const [dynamicStructures, setDynamicStructures] = useState<
    MolecularStructure[]
  >([]);
  const [generated, setGenerated] = useState<Candidate[]>([]);
  const [batchProvenance, setBatchProvenance] = useState<unknown>();
  const [loadError, setLoadError] = useState("");
  const [apiError, setApiError] = useState("");
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [loading, setLoading] = useState(!DEMO);
  const [submitting, setSubmitting] = useState(false);
  const submissionInFlight = useRef<Promise<string> | null>(null);
  const [health, setHealth] = useState<Health>({
    loading: !DEMO,
    connected: false,
    ready: false,
    generatorReady: false,
    workerReady: false,
    detail: "",
  });
  const [selectedId, setSelectedId] = useState(
    saved.selectedId ?? (saved.selectedRun && !DEMO ? "" : "1H1S"),
  );
  const explicitSelection = useRef(Boolean(saved.selectedId));
  const selectCandidate = useCallback((id: string) => {
    explicitSelection.current = true;
    setSelectedId(id);
  }, []);
  const [activeExperimentId, setActiveExperimentId] = useState<
    string | undefined
  >(undefined);
  const [pins, setPins] = useState(saved.pins);
  const [notes, setNotes] = useState(saved.drafts ?? saved.notes);
  const [savedNotes, setSavedNotes] = useState(saved.notes);
  const [noteSaving, setNoteSaving] = useState(false);
  const savedNotesRef = useRef(savedNotes);
  savedNotesRef.current = savedNotes;
  const [preferredPoses, setPreferredPoses] = useState<Record<string, string>>(
    saved.preferredPoses ?? {},
  );
  const preferredPosesRef = useRef(preferredPoses);
  preferredPosesRef.current = preferredPoses;
  const decisionsRef = useRef<Record<string, Decision>>({});
  const decisionEpoch = useRef(0);
  const pendingEdits = useRef(
    new Map<string, { token: number; change: DecisionChange }[]>(),
  );
  const pinsRef = useRef(pins);
  pinsRef.current = pins;
  const pendingDecisions = useRef(new Map<string, Promise<void>>());
  const inFlight = useRef(new Set<string>());
  const experimentsInFlight = useRef(new Map<string, Promise<void>>());
  const activeIdRef = useRef(activeExperimentId);
  activeIdRef.current = activeExperimentId;
  const loadedPoses = useRef(new Map<string, Promise<void>>());
  const poseStructures = useRef(new Map<string, MolecularStructure[]>());
  const requestedPose = useRef<string | undefined>(undefined);
  const candidatesRef = useRef(generated);
  candidatesRef.current = generated;
  const applyRecorded = useCallback((record: RecordedExperiment) => {
    const id = record.experiment.id;
    setGenerated(
      record.candidates.map((c) => ({
        ...normalizeCandidate(c, id),
        recorded: true,
      })),
    );
    setDynamicStructures(record.viewer.structures);
    setBatchProvenance(record.experiment.spec);
    setActiveExperimentId(id);
    activeIdRef.current = id;
    setSelectedId((previous) =>
      explicitSelection.current &&
      record.candidates.some((c) => c.id === previous)
        ? previous
        : (defaultCandidate(
            record.candidates.map((c) => normalizeCandidate(c, id)),
          )?.id ?? ""),
    );
    setPreferredPoses((previous) => ({
      ...Object.fromEntries(
        record.decisions
          .filter((d) => d.preferred_pose_id)
          .map((d) => [d.candidate_id, d.preferred_pose_id]),
      ),
      ...previous,
    }));
  }, []);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(
        UI_STORE,
        JSON.stringify({
          selectedRun: activeExperimentId,
          selectedId: explicitSelection.current ? selectedId : undefined,
          pins,
          notes: savedNotes,
          drafts: notes,
          preferredPoses,
        }),
      );
    } catch {
      /* session still works */
    }
  }, [activeExperimentId, selectedId, pins, savedNotes, notes, preferredPoses]);
  useEffect(() => {
    const hasDraft = Object.entries(notes).some(
      ([id, text]) => text !== (savedNotes[id] ?? ""),
    );
    if (!hasDraft && !submitting && !noteSaving) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [notes, savedNotes, submitting, noteSaving]);
  useEffect(() => {
    let alive = true;
    setLoadError("");
    loadMolecularDataset()
      .then((data) => {
        if (alive)
          setReferenceStructures(
            data.structures.filter((s) => s.origin === "observed"),
          );
      })
      .catch((e) => {
        if (alive) setLoadError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [referenceRetry]);
  const refreshHealth = useCallback(async () => {
    if (DEMO || inFlight.current.has("health")) return;
    inFlight.current.add("health");
    try {
      const raw = await request<RawRecord>("/experiments/readiness");
      if (!mounted.current) return;
      const ready = Boolean(raw.ready ?? raw.science_ready);
      setHealth({
        loading: false,
        connected: true,
        ready,
        generatorReady: Boolean(
          raw.libinvent_ready ??
            raw.generation_ready ??
            raw.capabilities?.libinvent,
        ),
        workerReady: Boolean(raw.worker?.online ?? raw.worker_ready ?? ready),
        detail:
          raw.message ??
          raw.detail ??
          (raw.checks
            ?.filter((check: RawRecord) => !check.ok)
            .map((check: RawRecord) => check.message)
            .join(" ") ||
            (ready
              ? "Local engine ready"
              : "Science environment needs attention")),
        raw,
      });
    } catch (e) {
      if (mounted.current)
        setHealth({
          loading: false,
          connected: false,
          ready: false,
          generatorReady: false,
          workerReady: false,
          detail:
            e instanceof Error ? e.message : "Cannot connect to the local API",
        });
    } finally {
      inFlight.current.delete("health");
    }
  }, []);

  const refreshRuns = useCallback(async () => {
    if (DEMO || inFlight.current.has("runs")) return;
    inFlight.current.add("runs");
    try {
      const data = await request<unknown>("/experiments");
      const next = listOf(data, "experiments").map(normalizeRun);
      // A directly opened older run may be outside the first list page.
      // Poll its small snapshot as well so remote changes and progress remain live.
      const selectedId = activeIdRef.current;
      if (selectedId && !next.some((run) => run.id === selectedId)) {
        try {
          next.push(
            normalizeRun(
              await request<RawRecord>(`/experiments/${selectedId}`),
            ),
          );
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) throw error;
        }
      }
      if (mounted.current) {
        setRuns(next);
        setLoading(false);
        setApiError((previous) =>
          previous.startsWith("Connection interrupted:") ? "" : previous,
        );
      }
    } catch (e) {
      if (mounted.current) {
        setApiError(
          "Connection interrupted: " +
            (e instanceof Error ? e.message : "Unable to load experiments"),
        );
        setLoading(false);
      }
    } finally {
      inFlight.current.delete("runs");
    }
  }, []);

  const loadExperiment = useCallback((id: string): Promise<void> => {
    if (DEMO) {
      setActiveExperimentId(id);
      return Promise.resolve();
    }
    const pending = experimentsInFlight.current.get(id);
    if (pending) return pending;
    const work = (async () => {
      try {
        const readEpoch = decisionEpoch.current;
        const [detail, rows, decisions] = await Promise.all([
          request<RawRecord>(`/experiments/${id}`),
          request<unknown>(`/experiments/${id}/candidates`),
          request<unknown>(`/experiments/${id}/decisions`),
        ]);
        if (!mounted.current || activeIdRef.current !== id) return;
        setRuns((prev) => {
          const row = normalizeRun(detail);
          return prev.some((r) => r.id === id)
            ? prev.map((r) => (r.id === id ? row : r))
            : [row, ...prev];
        });
        const next = listOf(rows, "candidates").map((r) =>
          normalizeCandidate(r, id),
        );
        setGenerated(next);
        setSelectedId((previous) =>
          explicitSelection.current && next.some((c) => c.id === previous)
            ? previous
            : defaultCandidate(next)?.id || "",
        );
        setBatchProvenance(detail.spec);
        // A response started before a local edit must not roll it back.
        if (
          readEpoch !== decisionEpoch.current ||
          pendingDecisions.current.size
        )
          return;
        const ds = listOf(decisions, "decisions");
        for (const decision of ds)
          decisionsRef.current[decision.candidate_id] = {
            pinned: decision.pinned,
            notes: decision.notes ?? "",
            preferred_pose_id: decision.preferred_pose_id ?? null,
            revision: decision.revision ?? 0,
          };
        setPreferredPoses((previous) => {
          const updated = { ...previous };
          for (const candidate of next) delete updated[candidate.id];
          for (const decision of ds)
            if (decision.preferred_pose_id)
              updated[decision.candidate_id] = decision.preferred_pose_id;
          return updated;
        });
        setPins((p) => [
          ...p.filter((candidateId) => !next.some((c) => c.id === candidateId)),
          ...ds.filter((d) => d.pinned).map((d) => d.candidate_id),
        ]);
        const remoteNotes = Object.fromEntries(
          ds.map((d) => [d.candidate_id, d.notes ?? ""]),
        );
        setNotes((previous) => {
          const next = { ...previous };
          for (const [id, note] of Object.entries(remoteNotes)) {
            if (
              previous[id] === undefined ||
              previous[id] === savedNotesRef.current[id]
            )
              next[id] = note as string;
          }
          return next;
        });
        setSavedNotes((p) => ({ ...p, ...remoteNotes }));
      } finally {
        experimentsInFlight.current.delete(id);
      }
    })();
    experimentsInFlight.current.set(id, work);
    return work;
  }, []);
  useEffect(() => {
    if (DEMO) return;
    const sync = () => {
      if (document.visibilityState === "visible") {
        void refreshRuns();
        void refreshHealth();
      }
    };
    sync();
    const timer = setInterval(sync, 4000);
    document.addEventListener("visibilitychange", sync);
    window.addEventListener("online", sync);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", sync);
      window.removeEventListener("online", sync);
    };
  }, [refreshHealth, refreshRuns]);
  // The small experiment snapshot is the invalidation signal. Heavy result rows
  // are fetched once per durable sequence change, never every idle interval.
  const activeSequence = runs.find(
    (run) => run.id === activeExperimentId,
  )?.latestSequence;
  useEffect(() => {
    if (DEMO || !activeExperimentId || !health.connected) return;
    let alive = true;
    void loadExperiment(activeExperimentId).catch((e) => {
      if (alive && !(e instanceof ApiError && e.status === 404))
        setApiError("Connection interrupted: " + e.message);
    });
    return () => {
      alive = false;
    };
  }, [activeExperimentId, activeSequence, health.connected, loadExperiment]);
  useEffect(() => {
    if (!DEMO) return;
    let alive = true;
    loadRecordedManifest()
      .then(async (manifest) => {
        if (manifest) {
          if (!alive) return;
          setRecordedExperiments(manifest.experiments);
          setRuns(
            manifest.experiments.map((record) => ({
              ...normalizeRun(record.experiment),
              recorded: true,
            })),
          );
          const record =
            manifest.experiments.find(
              (r) => r.experiment.id === activeIdRef.current,
            ) ?? manifest.experiments[0];
          if (record) applyRecorded(record);
          setLoading(false);
          return;
        }
        const [data, batch] = await Promise.all([
          loadMolecularDataset(),
          fetch("/data/generated-candidates.json").then((r) => r.json()),
        ]);
        if (!alive) return;
        const candidates = (batch.candidates ?? batch).map((c: Candidate) => ({
          ...c,
          recorded: true,
          depictionUrl: `./data/depictions/${c.id}.svg`,
        }));
        setGenerated(candidates);
        setDynamicStructures(
          data.structures.filter((s) => s.origin === "predicted"),
        );
        setBatchProvenance(batch.provenance);
        setActiveExperimentId("recorded-seed43");
        setRuns([
          {
            id: "recorded-seed43",
            name: "N2 exploration · recorded seed 43",
            createdAt: "2026-11-15T00:00:00Z",
            status: "completed_with_errors",
            stage: "review",
            candidateCount: candidates.length,
            config: {
              ...DEFAULT_EXPERIMENT,
              source: "libinvent",
              count: 32,
              maxCandidates: 24,
              conformers: 8,
            },
            elapsedSeconds: 273.4,
            objectiveHits: 0,
            completedCandidates: 24,
            poseFailureCount: 5,
            errorCount: 5,
            recorded: true,
            message:
              "24 candidates ready to inspect. Five pose attempts failed; successful siblings were preserved.",
          },
        ]);
      })
      .catch((e) => {
        if (alive) setLoadError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);
  const ensurePose = useCallback((poseId: string) => {
    requestedPose.current = poseId;
    const cached = poseStructures.current.get(poseId);
    if (cached) {
      poseStructures.current.delete(poseId);
      poseStructures.current.set(poseId, cached);
    }
    if (DEMO || loadedPoses.current.has(poseId) || !activeIdRef.current) return;
    const promise = request<{
      structures: MolecularStructure[];
      parentStructureId?: string;
    }>(
      `/experiments/${activeIdRef.current}/viewer?pose_id=${encodeURIComponent(poseId)}`,
    )
      .then((data) => {
        if (!mounted.current) return;
        const next = data.structures.map((raw) => ({
          ...raw,
          parentStructureId: data.parentStructureId,
          sdfUrl: artifactUrl(raw.sdfUrl),
        }));
        poseStructures.current.set(poseId, next);
        while (poseStructures.current.size > 12) {
          const oldest = [...poseStructures.current.keys()].find(
            (key) => key !== requestedPose.current,
          );
          if (!oldest) break;
          poseStructures.current.delete(oldest);
          loadedPoses.current.delete(oldest);
        }
        const merged = new Map<string, MolecularStructure>();
        for (const bundle of poseStructures.current.values())
          for (const structure of bundle) merged.set(structure.id, structure);
        setDynamicStructures([...merged.values()]);
      })
      .catch((e) => {
        loadedPoses.current.delete(poseId);
        if (mounted.current)
          setApiError(`Could not load this pose: ${e.message}`);
      });
    loadedPoses.current.set(poseId, promise);
  }, []);
  const openRun = useCallback(
    async (id: string) => {
      const previousId = activeIdRef.current;
      if (previousId !== id) explicitSelection.current = false;
      activeIdRef.current = id;
      setActiveExperimentId(id);
      if (DEMO) {
        const manifest = await loadRecordedManifest();
        if (manifest) {
          const record = manifest.experiments.find(
            (r) => r.experiment.id === id,
          );
          if (!record)
            throw new ApiError("Recorded experiment not found.", 404);
          applyRecorded(record);
        } else if (id !== "recorded-seed43")
          throw new ApiError("Recorded experiment not found.", 404);
      } else {
        if (previousId !== id) {
          setSelectedId("");
          setGenerated([]);
        }
        await loadExperiment(id);
      }
      return id;
    },
    [loadExperiment, applyRecorded],
  );
  const startRun = useCallback(
    (config: ExperimentConfig): Promise<string> => {
      if (submissionInFlight.current) return submissionInFlight.current;
      const payload = JSON.stringify(toRequest(config));
      const key = submissionKey(payload);
      setSubmitting(true);
      setApiError("");
      const work = (async () => {
        try {
          const result = await request<RawRecord>("/experiments", {
            method: "POST",
            headers: { "Idempotency-Key": key },
            body: payload,
          });
          const id = result.id ?? result.experiment_id;
          if (typeof id !== "string" || !id)
            throw new Error(
              "The engine returned an incomplete receipt. Retry to retrieve the same experiment.",
            );
          clearSubmissionKey(payload);
          await refreshRuns();
          try {
            await openRun(id);
          } catch {
            setApiError(
              "Experiment created, but its results could not be loaded. Reopen it from Experiments to retry.",
            );
          }
          return id;
        } catch (e) {
          if (e instanceof ApiError && [400, 404, 422].includes(e.status))
            clearSubmissionKey(payload);
          const message =
            e instanceof Error ? e.message : "Could not start experiment";
          setApiError(message);
          throw new Error(message);
        } finally {
          setSubmitting(false);
          submissionInFlight.current = null;
        }
      })();
      submissionInFlight.current = work;
      return work;
    },
    [refreshRuns, openRun],
  );
  const cancelRun = useCallback(
    async (id: string) => {
      try {
        await request(`/experiments/${id}/cancel`, { method: "POST" });
        await refreshRuns();
      } catch (e) {
        setApiError(
          e instanceof Error ? e.message : "Could not cancel the run",
        );
      }
    },
    [refreshRuns],
  );
  const saveDecision = useCallback(
    async (candidateId: string, change: DecisionChange) => {
      const candidate = candidatesRef.current.find((c) => c.id === candidateId);
      const initial = decisionsRef.current[candidateId] ?? {
        pinned: pinsRef.current.includes(candidateId),
        notes: savedNotesRef.current[candidateId] ?? "",
        preferred_pose_id: preferredPosesRef.current[candidateId] ?? null,
        revision: 0,
      };
      decisionsRef.current[candidateId] = initial;
      const token = ++decisionEpoch.current;
      pendingEdits.current.set(candidateId, [
        ...(pendingEdits.current.get(candidateId) ?? []),
        { token, change },
      ]);
      const publish = () => {
        const confirmed = decisionsRef.current[candidateId];
        const optimistic = (pendingEdits.current.get(candidateId) ?? []).reduce(
          (value, edit) => ({ ...value, ...edit.change }),
          confirmed,
        );
        setPins((previous) =>
          optimistic.pinned
            ? [...previous.filter((id) => id !== candidateId), candidateId]
            : previous.filter((id) => id !== candidateId),
        );
        setPreferredPoses((previous) => {
          const next = { ...previous };
          if (optimistic.preferred_pose_id)
            next[candidateId] = optimistic.preferred_pose_id;
          else delete next[candidateId];
          return next;
        });
        setSavedNotes((previous) => ({
          ...previous,
          [candidateId]: confirmed.notes,
        }));
      };
      publish();
      const previous =
        pendingDecisions.current.get(candidateId) ?? Promise.resolve();
      const work = previous
        .catch(() => {})
        .then(async () => {
          // Apply this patch to confirmed state when it reaches the queue head.
          // A failed earlier pin or pose edit can never leak into a later note save.
          const desired = { ...decisionsRef.current[candidateId], ...change };
          try {
            if (!DEMO && candidate?.experimentId) {
              const confirmed = await request<Decision>(
                `/experiments/${candidate.experimentId}/decisions/${candidateId}`,
                {
                  method: "PATCH",
                  headers: {
                    "If-Match": `"${decisionsRef.current[candidateId].revision}"`,
                  },
                  body: JSON.stringify(change),
                },
              );
              decisionsRef.current[candidateId] = confirmed;
            } else decisionsRef.current[candidateId] = desired;
          } catch (error) {
            if (error instanceof ApiError && error.status === 409) {
              const current = (error.detail as { current?: Decision })?.current;
              if (current && typeof current.revision === "number")
                decisionsRef.current[candidateId] = current;
            }
            throw error;
          } finally {
            pendingEdits.current.set(
              candidateId,
              (pendingEdits.current.get(candidateId) ?? []).filter(
                (edit) => edit.token !== token,
              ),
            );
            publish();
          }
        });
      pendingDecisions.current.set(candidateId, work);
      try {
        await work;
      } finally {
        if (pendingDecisions.current.get(candidateId) === work)
          pendingDecisions.current.delete(candidateId);
      }
    },
    [],
  );
  const preferPose = useCallback(
    async (candidateId: string, poseId: string) => {
      try {
        await saveDecision(candidateId, { preferred_pose_id: poseId });
        return true;
      } catch (e) {
        setApiError(
          e instanceof Error ? e.message : "Could not save the selected pose",
        );
        return false;
      }
    },
    [saveDecision],
  );
  const togglePin = useCallback(
    async (id: string) => {
      try {
        await saveDecision(id, { pinned: !pins.includes(id) });
      } catch (e) {
        setApiError(e instanceof Error ? e.message : "Could not save this pin");
      }
    },
    [pins, saveDecision],
  );
  const saveNote = useCallback(
    async (id: string) => {
      setNoteSaving(true);
      try {
        await saveDecision(id, { notes: notes[id] ?? "" });
      } catch (e) {
        setApiError(
          e instanceof Error ? e.message : "Could not save this note",
        );
      } finally {
        setNoteSaving(false);
      }
    },
    [notes, saveDecision],
  );
  const structures = useMemo(
    () => [...referenceStructures, ...dynamicStructures],
    [referenceStructures, dynamicStructures],
  );
  const candidates = useMemo(
    () => [...referenceStructures.map(referenceCandidate), ...generated],
    [referenceStructures, generated],
  );
  return {
    demo: DEMO,
    recordedExperiments,
    structures,
    generated,
    batchProvenance,
    candidates,
    loadError,
    refreshReferences: () => setReferenceRetry((n) => n + 1),
    apiError,
    clearError: () => setApiError(""),
    pins,
    notes,
    savedNotes,
    noteSaving,
    preferredPoses,
    preferPose,
    runs,
    loading,
    submitting,
    health,
    refreshHealth,
    refreshRuns,
    activeExperimentId,
    selectedId,
    setSelectedId: selectCandidate,
    startRun,
    openRun,
    cancelRun,
    ensurePose,
    togglePin,
    setNote: (id: string, text: string) =>
      setNotes((p) => ({ ...p, [id]: text })),
    saveNote,
  };
}
