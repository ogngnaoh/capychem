import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import {
  Link,
  useNavigate,
  type LinkProps,
  type NavigateOptions,
} from "react-router";
import { useWorkspace, DEMO } from "./useWorkspace";
import { DEFAULT_EXPERIMENT, type ExperimentConfig } from "./experimentConfig";
import { request } from "./api";
import { loadRecordedManifest } from "./recordedData";
export type Preset = {
  id: string;
  name: string;
  description: string;
  recommended?: boolean;
  default_spec: Record<string, any>;
  reference_candidates: { name: string; smiles: string }[];
  receptor_pdb_id?: string;
  parent: { name: string; pose_kind?: string; reference_label?: string };
  manifest: Record<string, any>;
  protocol_descriptor: Record<string, any>;
  scope?: string;
  limitations?: string[];
};

export type SetupDraft = {
  config: ExperimentConfig;
  step: number;
  parentName?: string;
  savedAt: string;
};
const DRAFT_KEY = `capychem-setup-draft-v2-${DEMO ? "demo" : "live"}`;
function readDraft(): SetupDraft | undefined {
  try {
    const value = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    const c = value?.config;
    if (
      !c ||
      typeof c.name !== "string" ||
      typeof c.suppliedText !== "string" ||
      !["supplied", "libinvent"].includes(c.source) ||
      !Number.isInteger(value.step) ||
      value.step < 0 ||
      value.step > 2
    )
      return;
    const defaults: ExperimentConfig = {
      ...DEFAULT_EXPERIMENT,
      maxMolecularWeight: 450,
      maxRotatableBonds: 8,
      evaluationSeconds: 600,
      embeddingSeed: 194715,
      vinaSeed: 42,
    };
    const ranges: Record<string, [number, number]> = {
      count: [2, 128],
      seed: [0, 2147483000],
      maxLogP: [-5, 10],
      maxCandidates: [1, 64],
      conformers: [1, 32],
      maxMolecularWeight: [100, 1000],
      maxRotatableBonds: [0, 30],
      evaluationSeconds: [10, 3600],
      embeddingSeed: [0, 2147483000],
      vinaSeed: [0, 2147483000],
    };
    const config = { ...defaults, ...c };
    for (const [key, [min, max]] of Object.entries(ranges))
      if (
        typeof c[key] !== "number" ||
        !Number.isFinite(c[key]) ||
        c[key] < min ||
        c[key] > max ||
        (key !== "maxLogP" && !Number.isInteger(c[key]))
      )
        config[key] = (defaults as any)[key];
    for (const key of ["parentId", "protocol", "targetPreparationId"])
      if (config[key] !== undefined && typeof config[key] !== "string")
        delete config[key];
    return {
      config,
      step: value.step,
      parentName:
        typeof value.parentName === "string" ? value.parentName : undefined,
      savedAt: typeof value.savedAt === "string" ? value.savedAt : "",
    };
  } catch {
    /* Optional local storage. */
  }
}
type StudioState = ReturnType<typeof useWorkspace> & {
  presets: Preset[];
  presetsLoading: boolean;
  presetsError: string;
  refreshPresets: () => void;
  draft?: SetupDraft;
  saveDraft: (draft: SetupDraft) => void;
  clearDraft: () => void;
};
const StudioContext = createContext<StudioState | null>(null);
export function StudioProvider({ children }: { children: ReactNode }) {
  const workspace = useWorkspace();
  const [presets, setPresets] = useState<Preset[]>([]),
    [presetsLoading, setPresetsLoading] = useState(true),
    [presetsError, setPresetsError] = useState(""),
    [presetRetry, setPresetRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setPresetsLoading(true);
    const get = DEMO
      ? loadRecordedManifest().then((m) => m?.presets)
      : request<{ presets: Preset[] }>("/experiments/presets");
    get
      .then((data) => {
        if (alive) {
          setPresets(data?.presets ?? []);
          setPresetsError("");
        }
      })
      .catch((e) => {
        if (alive) setPresetsError(e.message);
      })
      .finally(() => alive && setPresetsLoading(false));
    return () => {
      alive = false;
    };
  }, [presetRetry]);

  const [draft, setDraft] = useState<SetupDraft | undefined>(readDraft);
  const saveDraft = useCallback((value: SetupDraft) => {
    setDraft(value);
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(value));
    } catch {
      /* Current session remains usable. */
    }
  }, []);
  const clearDraft = useCallback(() => {
    setDraft(undefined);
    try {
      localStorage.removeItem(DRAFT_KEY);
    } catch {
      /* Current session remains usable. */
    }
  }, []);
  return (
    <StudioContext.Provider
      value={{
        ...workspace,
        presets,
        presetsLoading,
        presetsError,
        refreshPresets: () => setPresetRetry((n) => n + 1),
        draft,
        saveDraft,
        clearDraft,
      }}
    >
      {children}
    </StudioContext.Provider>
  );
}
export function useStudio() {
  const value = useContext(StudioContext);
  if (!value) throw new Error("StudioProvider is required");
  return value;
}
export function studioPath(path: string) {
  if (!DEMO) return path;
  const [base, hash] = path.split("#");
  const url = new URL(base, location.origin);
  url.searchParams.set("mode", "demo");
  return `${url.pathname}${url.search}${hash ? `#${hash}` : ""}`;
}
export function StudioLink({ to, ...props }: LinkProps) {
  return <Link {...props} to={typeof to === "string" ? studioPath(to) : to} />;
}
export function useStudioNavigate() {
  const navigate = useNavigate();
  return (path: string, options?: NavigateOptions) =>
    navigate(studioPath(path), options);
}

export function protocolLabel(id?: string) {
  return id === "guided_growth_cdk2_v2"
    ? "Template-guided local refinement · v2"
    : id === "guided_local_cdk2_v1" || !id
      ? "Parent-guided local refinement · v1"
      : id;
}
