/** Shared molecular artifact cache. This module has no rendering dependencies.
 * Workspace evidence and the lazily loaded viewport share one fetch, one JSON
 * parse, and the same expanded structure objects for this immutable fixture. */
export type StructureId = string;
export type Vec3 = [number, number, number];
export type MolecularAtom = {
  id: string;
  index: number;
  name: string;
  element: string;
  position: Vec3;
  scaffold?: boolean;
  purine?: boolean;
  attachment?: boolean;
  extension?: boolean;
  residue?: string;
  residueId?: string;
  residueNumber?: number;
  chain?: string;
};
export type MolecularLigandAtom = MolecularAtom & {
  scaffold: boolean;
  purine: boolean;
  attachment: boolean;
  extension: boolean;
};
export type MolecularBond = {
  a: string;
  b: string;
  order?: number;
  aromatic?: boolean;
};
export type MolecularContact = {
  id: string;
  ligandAtom: string;
  proteinAtom: string;
  residueId: string;
  residueLabel: string;
  kind: string;
  distance: number;
  angle?: number;
  provenance: string;
};
export type MolecularStructure = {
  id: StructureId;
  compound: string;
  component: string;
  origin: "observed" | "predicted" | "template";
  referencePoseKind?: string;
  receptorId: string;
  sourceUrl: string;
  coordinateNote: string;
  alignment: {
    reference: string;
    atomCount: number;
    method: string;
    backboneRmsd: number;
  };
  ligandAtoms: MolecularLigandAtom[];
  ligandBonds: MolecularBond[];
  pocketAtoms: MolecularAtom[];
  pocketBonds: MolecularBond[];
  backboneAtoms: MolecularAtom[];
  contacts: MolecularContact[];
  parentStructureId?: string;
  sdfUrl?: string;
  sdfCoordinateFrame?: string;
  properties: {
    smiles: string;
    molecular_weight: number;
    clogp: number;
    formal_charge: number;
    rotatable_bonds: number;
    heavy_atoms: number;
    ligand_occupancies?: number[];
  };
};
export type MolecularDataset = {
  structures: MolecularStructure[];
  predictionBatch?: unknown;
  [key: string]: unknown;
};
type RawStructure = Omit<MolecularStructure, "backboneAtoms"> & {
  backboneAtoms?: MolecularAtom[];
  backboneRef?: string;
};
let datasetPromise: Promise<MolecularDataset> | undefined;

export function loadMolecularDataset(): Promise<MolecularDataset> {
  return (datasetPromise ??= fetch("./data/cdk2-references.json")
    .then((response) => {
      if (!response.ok)
        throw new Error("Unable to load the molecular reference dataset.");
      return response.json();
    })
    .then((data) => {
      if (!Array.isArray(data?.structures))
        throw new Error("The molecular dataset has no structures.");
      const raw = data.structures as RawStructure[];
      const byId = new Map(raw.map((structure) => [structure.id, structure]));
      const structures = raw.map((structure) => {
        const backboneAtoms = structure.backboneRef
          ? byId.get(structure.backboneRef)?.backboneAtoms
          : structure.backboneAtoms;
        if (!backboneAtoms)
          throw new Error(`Missing protein context for ${structure.id}.`);
        return { ...structure, backboneAtoms };
      });
      return { ...data, structures } as MolecularDataset;
    })
    .catch((error) => {
      // Failure is not cached permanently; a later mount can retry.
      datasetPromise = undefined;
      throw error;
    }));
}

export function loadMolecularStructures(): Promise<MolecularStructure[]> {
  return loadMolecularDataset().then((data) => data.structures);
}
