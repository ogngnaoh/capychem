import type { ExperimentRun } from "./experimentModel";
import type { ExperimentConfig } from "./experimentConfig";
import type { HydrogenPreparation } from "./data";
export type SeedPair = { embedding: number; vina: number };
export type StudyContact = {
  type: string;
  protein_atom_name: string;
  ligand_atom_index: number;
  distance_A: number;
  angle_degrees?: number;
};
export const DEFAULT_STUDY_SEEDS: SeedPair[] = [
  { embedding: 194715, vina: 42 },
  { embedding: 41821, vina: 43 },
  { embedding: 61531, vina: 44 },
];
export type StudyObservation = {
  run_ordinal: number;
  seeds: SeedPair;
  experiment_status: ExperimentRun["status"];
  execution_complete: boolean;
  experiment_id: string;
  attempt_id?: string | null;
  candidate_id?: string | null;
  status: string;
  selected_pose_id?: string | null;
  normalized_smiles?: string | null;
  prepared_smiles?: string | null;
  prepared_state_id?: string | null;
  unspecified_stereochemistry?: boolean;
  stereochemistry_note?: string | null;
  score?: number | null;
  review_ready?: boolean | null;
  asp86_contact?: boolean | null;
  error?: string | null;
  filter_failures?: string[];
  duplicate_of_candidate_id?: string | null;
  asp86_contacts?: StudyContact[] | null;
  hydrogen_preparation?: HydrogenPreparation | null;
};
export type StudyCandidate = {
  candidate_index: number;
  name: string;
  smiles: string;
  planned_runs: number;
  completed_runs: number;
  observed_runs: number;
  review_ready_runs: number;
  contact_hit_runs: number;
  observations: StudyObservation[];
};
export type Study = {
  id: string;
  label: string;
  created_at: string;
  status: ExperimentRun["status"];
  base_spec: Record<string, any>;
  spec_hash: string;
  seed_pairs: SeedPair[];
  counts: Record<string, number>;
  members: {
    ordinal: number;
    seeds: SeedPair;
    experiment: Record<string, any>;
  }[];
  candidates?: StudyCandidate[];
  export_url?: string;
};
export type StudySummary = Omit<Study, "candidates">;
export type StudyDraft = {
  config: ExperimentConfig;
  seeds: SeedPair[];
  step: number;
  sourceName?: string;
};
export const studyActive = (s: Study) =>
  ["queued", "running"].includes(s.status);
export const studyDraftKey = (demo: boolean) =>
  `capychem-study-draft-v1-${demo ? "demo" : "live"}`;
const memoryDrafts = new Map<string, StudyDraft>();
export function saveStudyDraft(demo: boolean, draft: StudyDraft) {
  memoryDrafts.set(studyDraftKey(demo), draft);
  try {
    localStorage.setItem(studyDraftKey(demo), JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}
export function clearStudyDraft(demo: boolean) {
  memoryDrafts.delete(studyDraftKey(demo));
  try {
    localStorage.removeItem(studyDraftKey(demo));
  } catch {
    /* Current draft is cleared. */
  }
}
export function readStudyDraft(demo: boolean): StudyDraft | undefined {
  if (memoryDrafts.has(studyDraftKey(demo)))
    return memoryDrafts.get(studyDraftKey(demo));
  try {
    const d = JSON.parse(localStorage.getItem(studyDraftKey(demo)) || "null");
    if (
      !d ||
      typeof d.config?.name !== "string" ||
      typeof d.config?.suppliedText !== "string" ||
      !["supplied", "libinvent"].includes(d.config.source) ||
      !["count", "seed", "maxLogP", "maxCandidates", "conformers"].every(
        (key) =>
          typeof d.config[key] === "number" && Number.isFinite(d.config[key]),
      ) ||
      !["protocol", "targetPreparationId", "parentId"].every(
        (key) =>
          d.config[key] === undefined || typeof d.config[key] === "string",
      ) ||
      ![
        "maxMolecularWeight",
        "maxRotatableBonds",
        "evaluationSeconds",
        "embeddingSeed",
        "vinaSeed",
      ].every(
        (key) =>
          d.config[key] === undefined ||
          (typeof d.config[key] === "number" && Number.isFinite(d.config[key])),
      ) ||
      !Array.isArray(d.seeds) ||
      d.seeds.length < 2 ||
      d.seeds.length > 8 ||
      !d.seeds.every(
        (s: SeedPair) =>
          Number.isInteger(s.embedding) &&
          Number.isInteger(s.vina) &&
          s.embedding >= 0 &&
          s.vina >= 0 &&
          s.embedding <= 2147483000 &&
          s.vina <= 2147483000,
      ) ||
      !Number.isInteger(d.step) ||
      d.step < 0 ||
      d.step > 2
    )
      return;
    return d;
  } catch {
    return;
  }
}
