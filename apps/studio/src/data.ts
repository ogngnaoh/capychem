export interface Contact {
  id: string;
  ligandAtom: string;
  proteinAtom: string;
  residueId: string;
  residueLabel: string;
  kind: string;
  distance: number;
  angle?: number;
  provenance: string;
}
export interface HydrogenPreparation {
  policy: string;
  method: string;
  note: string;
  orientation_optimized_against_receptor: boolean;
  orientation_sensitivity_assessed: boolean;
  oh_groups: {
    oxygen_atom_index: number;
    hydrogen_atom_index: number;
    carbon_atom_index: number;
  }[];
  warnings: { code: string; message: string }[];
}
export interface Structure {
  id: string;
  compound: string;
  component: string;
  origin: string;
  receptorId: string;
  sourceUrl: string;
  coordinateNote: string;
  sdfUrl?: string;
  contacts: Contact[];
  pocketAtoms?: { id: string; name: string; element: string }[];
  hydrogenPreparation?: HydrogenPreparation;
  alignment: { backboneRmsd: number; atomCount: number };
  properties: {
    smiles: string;
    molecular_weight: number;
    clogp: number;
    formal_charge: number;
    rotatable_bonds: number;
    heavy_atoms: number;
    ligand_occupancies?: number[];
  };
  ligandAtoms: {
    id: string;
    name: string;
    scaffold: boolean;
    purine: boolean;
    attachment: boolean;
    extension: boolean;
  }[];
}
export interface CandidatePose {
  structureId: string;
  label: string;
  score?: number;
  checks: "pass" | "fail" | "unavailable";
  contacts: number;
  ringDriftA?: number;
  reviewReady: boolean;
  asp86Contact?: boolean;
  smiles?: string;
  sdfUrl?: string;
  preparedStateId?: string;
  preparedMoleculeId?: string;
  preparedSmiles?: string;
  failures?: string[];
}
export interface Candidate {
  id: string;
  sourceId?: string;
  duplicateOfSourceId?: string;
  duplicateOfCandidateId?: string;
  error?: string;
  name: string;
  description: string;
  origin: "observed" | "generated";
  structureId?: string;
  receptorId: string;
  smiles: string;
  mw: number;
  clogp: number;
  rotors: number;
  charge?: number;
  contacts: number;
  checks: "pass" | "fail" | "unavailable";
  failures: string[];
  score?: number;
  poseCount?: number;
  sourceUrl?: string;
  ringDriftA?: number;
  reviewReady?: boolean;
  status?: string;
  selectionPolicy?: string;
  asp86Contact?: boolean;
  proposalSmiles?: string;
  stereochemistryNote?: string;
  unspecifiedStereochemistry?: boolean;
  partial?: boolean;
  poseErrors?: { id: string; kind: string; message: string }[];
  embeddingErrors?: {
    attempt: number;
    seed: number;
    status: string;
    error: string;
  }[];
  poses?: CandidatePose[];
  depictionUrl?: string;
  recorded?: boolean;
  experimentId?: string;
  selectedPoseId?: string;
  preparedMoleculeId?: string;
}
export const descriptions: Record<string, string> = {
  "1H1P": "Starting ligand",
  "1H1Q": "Anilino extension",
  "1H1R": "Chloro extension",
  "1H1S": "Sulfonamide extension",
};
export const labels: Record<string, string> = {
  minimum_distance_to_protein: "Too close to protein",
  volume_overlap_with_protein: "Protein overlap",
  molecular_weight: "Molecular weight",
  clogp: "cLogP ceiling",
  rotatable_bonds: "Flexibility limit",
  parent_scaffold_not_retained: "Parent scaffold not retained",
  invalid_smiles: "Invalid molecular structure",
  unspecified_stereochemistry: "Unspecified stereochemistry",
};
export const failureLabel = (s: string) => labels[s] ?? s.replaceAll("_", " ");
export function referenceCandidate(s: Structure): Candidate {
  return {
    id: s.id,
    name: s.compound,
    description: descriptions[s.id] ?? s.compound,
    origin: "observed",
    structureId: s.id,
    receptorId: s.receptorId,
    smiles: s.properties.smiles,
    mw: s.properties.molecular_weight,
    clogp: s.properties.clogp,
    rotors: s.properties.rotatable_bonds,
    charge: s.properties.formal_charge,
    contacts: s.contacts.length,
    checks: "pass",
    failures: [],
    sourceUrl: s.sourceUrl,
    depictionUrl: `./data/depictions/${s.id}.svg`,
  };
}
export function download(
  name: string,
  content: string,
  type = "application/json",
) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const displayNumber = (value: number | undefined, digits = 2) =>
  Number.isFinite(value) ? value!.toFixed(digits) : "—";
