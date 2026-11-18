export type ExperimentConfig = {
  name: string;
  source: "supplied" | "libinvent";
  count: number;
  seed: number;
  maxLogP: number;
  maxCandidates: number;
  conformers: number;
  suppliedText: string;
  parentId?: string;
  protocol?: string;
  targetPreparationId?: string;
  maxMolecularWeight?: number;
  maxRotatableBonds?: number;
  evaluationSeconds?: number;
  embeddingSeed?: number;
  vinaSeed?: number;
  originCandidates?: OriginCandidate[];
};
export type CandidateOrigin = {
  candidate_index: number;
  experiment_id: string;
  candidate_id: string;
  pose_id?: string;
};
export type OriginCandidate = {
  name: string;
  smiles: string;
  origin: Omit<CandidateOrigin, "candidate_index">;
};
export function candidateOrigins(config: ExperimentConfig): CandidateOrigin[] {
  return parseCandidates(config.suppliedText).flatMap((entry, index) => {
    const source = Array.isArray(config.originCandidates)
      ? config.originCandidates.find(
          (c) =>
            c?.smiles === entry.smiles &&
            typeof c.origin?.experiment_id === "string" &&
            typeof c.origin?.candidate_id === "string",
        )
      : undefined;
    return source ? [{ ...source.origin, candidate_index: index }] : [];
  });
}
export const KNOWN_COMPOUNDS = [
  { name: "NU2058", smiles: "Nc1nc(OCC2CCCCC2)c2nc[nH]c2n1" },
  { name: "NU6094", smiles: "c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1" },
  { name: "NU6086", smiles: "Clc1cccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)c1" },
  {
    name: "NU6102",
    smiles: "NS(=O)(=O)c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1",
  },
];
export const DEFAULT_EXPERIMENT: ExperimentConfig = {
  name: "CDK2 · first design round",
  source: "supplied",
  count: 16,
  seed: 43,
  maxLogP: 4.5,
  maxCandidates: 8,
  conformers: 4,
  suppliedText: KNOWN_COMPOUNDS.map((c) => `${c.smiles} ${c.name}`).join("\n"),
};
export function parseCandidates(text: string) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const [smiles, ...name] = line.split(/\s+/);
      return { smiles, name: name.join(" ") || `Candidate ${index + 1}` };
    });
}
