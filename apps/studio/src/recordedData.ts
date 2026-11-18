import type { MolecularStructure } from "./molecularData";
import type { Study } from "./studyModel";
export type RecordedExperiment = {
  experiment: Record<string, any>;
  candidates: Record<string, any>[];
  decisions: Record<string, any>[];
  attempts: Record<string, any>[];
  events: Record<string, any>[];
  viewer: {
    structures: MolecularStructure[];
    sharedBackbones?: Record<string, MolecularStructure["backboneAtoms"]>;
  };
  export_url: string;
};
export type RecordedManifest = {
  schema_version: number;
  kind: "recorded_experiments";
  recorded_at: string;
  presets: Record<string, any>;
  experiments: RecordedExperiment[];
  studies?: Study[];
};
let pending: Promise<RecordedManifest | undefined> | undefined;
export function loadRecordedManifest() {
  return (pending ??= fetch("/data/recorded-experiments.json")
    .then(async (response) => {
      if (response.status === 404) return undefined;
      const type = response.headers.get("content-type");
      if (!type?.includes("json")) return undefined;
      if (!response.ok)
        throw new Error(
          "The recorded experiment manifest could not be loaded.",
        );
      const data = await response.json();
      if (
        data.kind !== "recorded_experiments" ||
        !Array.isArray(data.experiments)
      )
        throw new Error("The recorded experiment manifest is invalid.");
      for (const record of data.experiments) {
        const shared = record.viewer?.sharedBackbones ?? {};
        record.viewer.structures = record.viewer.structures.map(
          (structure: any) => {
            const backboneAtoms =
              structure.backboneAtoms ?? shared[structure.backboneRef];
            if (!Array.isArray(backboneAtoms))
              throw new Error(
                `Missing protein backbone for recorded structure ${structure.id}.`,
              );
            return { ...structure, backboneAtoms };
          },
        );
      }
      return data as RecordedManifest;
    })
    .catch((error) => {
      pending = undefined;
      throw error;
    }));
}
