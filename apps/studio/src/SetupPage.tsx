import { useEffect, useState, useRef, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { Button } from "@astryxdesign/core/Button";
import { TextInput } from "@astryxdesign/core/TextInput";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FlaskConical,
  Layers,
  LockKeyhole,
  Sparkles,
  TriangleAlert,
  Info,
} from "lucide-react";
import {
  useStudio,
  StudioLink,
  useStudioNavigate,
  protocolLabel,
} from "./StudioContext";
import {
  DEFAULT_EXPERIMENT,
  KNOWN_COMPOUNDS,
  parseCandidates,
  type ExperimentConfig,
} from "./experimentConfig";
import { fromSpec, toRequest } from "./useWorkspace";
import { request, ApiError } from "./api";
import { loadRecordedManifest } from "./recordedData";
import { InlineError, LoadingState, PageHeader } from "./ProductUI";
const STEPS = ["Candidates", "Rules & budget", "Review"];
const ranges = {
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
} as const;
export function SetupPage() {
  const w = useStudio(),
    navigate = useStudioNavigate();
  const [params] = useSearchParams();
  const from = params.get("from");
  const presetInitialized = useRef(Boolean(w.draft) || Boolean(from));
  const submitLock = useRef(false);
  const [launching, setLaunching] = useState(false);
  const [config, setConfig] = useState<ExperimentConfig>(() => ({
    ...DEFAULT_EXPERIMENT,
    ...w.draft?.config,
  }));
  const [step, setStep] = useState(w.draft?.step ?? 0);
  const [parentName, setParentName] = useState(w.draft?.parentName);
  const [loading, setLoading] = useState(
    Boolean(from && from !== w.draft?.config.parentId),
  );
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (!from || from === config.parentId) return;
    let alive = true;
    setLoading(true);
    const local = w.runs.find((r) => r.id === from);
    const get = local
      ? Promise.resolve(local.config)
      : w.demo
        ? loadRecordedManifest().then((manifest) => {
            const record = manifest?.experiments.find(
              (r) => r.experiment.id === from,
            );
            if (record)
              return fromSpec(
                record.experiment.spec?.request ?? record.experiment.spec,
                record.experiment.label,
              );
            if (!manifest && from === "recorded-seed43")
              return {
                ...DEFAULT_EXPERIMENT,
                name: "N2 exploration · recorded seed 43",
                source: "libinvent" as const,
                count: 32,
                maxCandidates: 24,
                conformers: 8,
              };
            throw new ApiError("Recorded source experiment not found.", 404);
          })
        : request<any>(`/experiments/${encodeURIComponent(from)}`).then((r) =>
            fromSpec(r.spec?.request ?? r.spec, r.label),
          );
    get
      .then((c) => {
        if (alive) {
          setConfig({
            ...c,
            parentId: from,
            name: `${c.name} · next round`.slice(0, 160),
          });
          setParentName(c.name);
          setStep(0);
          setError("");
        }
      })
      .catch(
        (e) =>
          alive &&
          setError(`Could not load the source experiment: ${e.message}`),
      )
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [from]);
  useEffect(() => {
    if (loading) return;
    w.saveDraft({
      config,
      step,
      parentName,
      savedAt: new Date().toISOString(),
    });
    setSaved(true);
  }, [config, step, parentName, loading, w.saveDraft]);
  const preset = w.presets.find(
    (p) => p.id === (config.targetPreparationId ?? "cdk2_1h1p"),
  );
  useEffect(() => {
    if (presetInitialized.current || !w.presets.length) return;
    presetInitialized.current = true;
    const p = w.presets.find((p) => p.recommended) ?? w.presets[0];
    setConfig(fromSpec(p.default_spec, p.default_spec.label));
  }, [w.presets]);
  useEffect(() => {
    window.scrollTo(0, 0);
    document
      .querySelector<HTMLElement>(".setup-main h2")
      ?.focus({ preventScroll: true });
  }, [step]);
  const changePreset = (id: string) => {
    const next = w.presets.find((p) => p.id === id);
    if (!next) return;
    const values = fromSpec(next.default_spec, next.default_spec.label);
    setConfig((c) => ({ ...values, name: c.name, parentId: c.parentId }));
  };
  const change = <K extends keyof ExperimentConfig>(
    key: K,
    value: ExperimentConfig[K],
  ) => {
    presetInitialized.current = true;
    setConfig((c) => ({ ...c, [key]: value }));
  };
  const entries = parseCandidates(config.suppliedText);
  const inputError = !config.name.trim()
    ? "Give the experiment a name."
    : config.name.length > 160
      ? "Keep the name within 160 characters."
      : config.source === "supplied" &&
          (entries.length < 1 || entries.length > 128)
        ? "Add between 1 and 128 candidates."
        : config.source === "supplied" &&
            entries.some((e) => e.smiles.length > 4096 || e.name.length > 160)
          ? "Use a SMILES up to 4096 characters and a name up to 160 characters per line."
          : "";
  const rangeError = Object.entries(ranges).find(([key, [min, max]]) => {
    const value = config[key as keyof ExperimentConfig];
    return (
      value !== undefined &&
      (typeof value !== "number" ||
        !Number.isFinite(value) ||
        value < min ||
        value > max ||
        (key !== "maxLogP" && !Number.isInteger(value)))
    );
  });
  const ready =
    w.health.ready &&
    (config.source !== "libinvent" || w.health.generatorReady) &&
    !w.demo &&
    Boolean(preset) &&
    !w.presetsLoading;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (inputError) {
      setStep(0);
      setError(inputError);
      return;
    }
    if (rangeError) {
      setStep(1);
      setError("Check the highlighted numerical limits.");
      return;
    }
    setError("");
    if (step < 2) {
      setStep(step + 1);
      return;
    }
    if (!ready || w.submitting || submitLock.current) return;
    submitLock.current = true;
    setLaunching(true);
    try {
      const id = await w.startRun({ ...config, name: config.name.trim() });
      w.clearDraft();
      navigate(`/experiments/${id}/activity`);
    } catch (e) {
      submitLock.current = false;
      setLaunching(false);
      setError(
        e instanceof Error ? e.message : "The experiment could not be started.",
      );
    }
  };
  const numeric = (
    key: keyof typeof ranges,
    label: string,
    defaultValue: number,
    help?: string,
  ) => {
    const [min, max] = ranges[key];
    const value = config[key] ?? defaultValue;
    const invalid =
      !Number.isFinite(value) ||
      value < min ||
      value > max ||
      (key !== "maxLogP" && !Number.isInteger(value));
    return (
      <label className="setup-number" key={key}>
        <span>{label}</span>
        <input
          type="number"
          aria-invalid={invalid}
          min={min}
          max={max}
          step={key === "maxLogP" ? 0.1 : 1}
          value={Number.isNaN(value) ? "" : value}
          onChange={(e) =>
            change(key, e.target.value === "" ? NaN : Number(e.target.value))
          }
        />
        {help && <small>{help}</small>}
      </label>
    );
  };
  if (loading)
    return (
      <section className="product-page">
        <PageHeader title="New experiment" />
        <LoadingState label="Loading the original settings…" />
      </section>
    );
  return (
    <section className="product-page setup-page flow-v5">
      <PageHeader
        title="New experiment"
        description="Define the candidates, limits and evidence you want to inspect."
        actions={
          <StudioLink className="text-link" to="/experiments">
            Save and exit
          </StudioLink>
        }
      />
      <ol className="setup-steps" aria-label="Experiment setup">
        {STEPS.map((label, i) => (
          <li
            key={label}
            className={i === step ? "current" : i < step ? "done" : ""}
          >
            <button
              type="button"
              onClick={() => {
                if (i < step) {
                  setStep(i);
                  setError("");
                }
              }}
              disabled={i > step}
              aria-current={i === step ? "step" : undefined}
            >
              <span>{i < step ? <Check size={14} /> : i + 1}</span>
              {label}
            </button>
          </li>
        ))}
      </ol>
      <form onSubmit={submit} noValidate>
        <div className="setup-columns">
          <div className="setup-main">
            {error && <InlineError message={error} />}
            {config.parentId && (
              <p className="fork-context">
                New round from{" "}
                <StudioLink to={`/experiments/${config.parentId}`}>
                  {parentName ?? config.parentId.slice(0, 8)}
                </StudioLink>
                . Copies its settings and inputs. Review them before starting a
                new run.
              </p>
            )}
            {step === 0 && (
              <>
                <h2 tabIndex={-1}>Choose your candidates</h2>
                <p className="section-description">
                  Evaluate a molecular series, or ask LibInvent for new side
                  groups.
                </p>
                <label className="preset-selector">
                  <span>Reference preparation</span>
                  <select
                    aria-label="Reference preparation"
                    value={config.targetPreparationId ?? "cdk2_1h1p"}
                    disabled={!w.presets.length}
                    onChange={(e) => changePreset(e.target.value)}
                  >
                    {w.presets.length ? (
                      w.presets.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                          {p.recommended ? " · Recommended" : ""}
                        </option>
                      ))
                    ) : (
                      <option value={config.targetPreparationId ?? "cdk2_1h1p"}>
                        {w.presetsLoading
                          ? "Loading preparations…"
                          : "Connect the engine to load preparations"}
                      </option>
                    )}
                  </select>
                  {preset && <small>{preset.description}</small>}
                </label>
                {w.presetsError && (
                  <InlineError
                    message="Reference preparations could not be loaded. Your draft is preserved."
                    onRetry={w.refreshPresets}
                  />
                )}
                <TextInput
                  label="Experiment name"
                  value={config.name}
                  onChange={(v) => change("name", v)}
                  placeholder="For example, CDK2 para growth"
                  width="100%"
                />
                <div
                  className="source-options"
                  role="radiogroup"
                  aria-label="Candidate source"
                >
                  {(
                    [
                      {
                        kind: "supplied",
                        label: "Evaluate candidates",
                        description: "Bring a series of SMILES.",
                        icon: FlaskConical,
                      },
                      {
                        kind: "libinvent",
                        label: "Generate variants",
                        description: "Explore side groups with LibInvent.",
                        icon: Sparkles,
                      },
                    ] as const
                  ).map(({ kind, label, description, icon: Icon }) => (
                    <label
                      className={config.source === kind ? "selected" : ""}
                      key={kind}
                    >
                      <input
                        type="radio"
                        name="source"
                        value={kind}
                        checked={config.source === kind}
                        onChange={() => change("source", kind)}
                      />
                      <Icon size={22} />
                      <strong>{label}</strong>
                      <span>{description}</span>
                      <i aria-hidden="true" />
                    </label>
                  ))}
                </div>
                {config.source === "supplied" ? (
                  <div className="candidate-input-field">
                    <div className="field-heading">
                      <label htmlFor="candidate-input">Candidates</label>
                      <Button
                        label="Use reference series"
                        variant="secondary"
                        size="sm"
                        onClick={() =>
                          change(
                            "suppliedText",
                            (preset?.reference_candidates ?? KNOWN_COMPOUNDS)
                              .map((c) => `${c.smiles} ${c.name}`)
                              .join("\n"),
                          )
                        }
                      />
                    </div>
                    <div className="flow-input-preview" aria-label="Supplied candidate names">
                      <div>
                        <strong>Inputs to evaluate</strong>
                        <span>{entries.length} supplied</span>
                      </div>
                      {entries.length ? (
                        <ol>
                          {entries.map((entry, index) => (
                            <li key={index}>
                              <span>{String(index + 1).padStart(2, "0")}</span>
                              {entry.name}
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p>Add a SMILES and optional name below.</p>
                      )}
                    </div>
                    <textarea
                      id="candidate-input"
                      spellCheck={false}
                      value={config.suppliedText}
                      onChange={(e) => change("suppliedText", e.target.value)}
                      rows={7}
                    />
                    <p className="field-help">
                      One SMILES and an optional name per line. {entries.length}{" "}
                      {entries.length === 1 ? "candidate" : "candidates"}{" "}
                      supplied.
                    </p>
                    <p className="field-help">
                      Invalid molecules, duplicates and scaffold mismatches stay
                      in the results with their reason for exclusion.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="setup-number-grid">
                      {numeric(
                        "count",
                        "Raw proposals",
                        16,
                        "Includes duplicates and proposals that fail screening.",
                      )}
                      {numeric(
                        "seed",
                        "Generation seed",
                        43,
                        "Same model and seed reproduce the proposal request.",
                      )}
                    </div>
                    <div className="info-block">
                      <Sparkles size={18} />
                      <p>
                        LibInvent proposes side groups around the declared
                        parent scaffold. RDKit and the pose pipeline then
                        evaluate them.
                      </p>
                    </div>
                    {!w.health.generatorReady && !w.demo && (
                      <InlineError message="LibInvent is not ready on the local engine. You can finish this draft and install its environment before running." />
                    )}
                  </>
                )}
              </>
            )}
            {step === 1 && (
              <>
                <h2 tabIndex={-1}>Set the rules and budget</h2>
                <p className="section-description">
                  Screen the proposed molecules, then evaluate a bounded number
                  of poses.
                </p>
                <h3>Property limits</h3>
                <div className="setup-number-grid">
                  {numeric(
                    "maxMolecularWeight",
                    "Maximum molecular weight",
                    450,
                    "g/mol",
                  )}
                  {numeric(
                    "maxLogP",
                    "Maximum calculated logP",
                    4.5,
                    "An estimate of lipophilicity",
                  )}
                  {numeric("maxRotatableBonds", "Maximum rotatable bonds", 8)}
                  <div className="fixed-field">
                    <span>Formal charge</span>
                    <strong>Neutral · 0</strong>
                    <small>Fixed by this protocol</small>
                  </div>
                </div>
                <h3>Calculation budget</h3>
                <div className="setup-number-grid">
                  {numeric("maxCandidates", "Maximum unique candidates", 8)}
                  {numeric(
                    "conformers",
                    "Embedding attempts per candidate",
                    4,
                    "Starting 3D arrangements to try. Fewer distinct poses may succeed.",
                  )}
                  {numeric(
                    "evaluationSeconds",
                    "Admission time limit",
                    600,
                    "Seconds. An admitted candidate finishes at a safe checkpoint.",
                  )}
                </div>
                <details className="setup-advanced">
                  <summary>Reproducibility settings</summary>
                  <div className="setup-number-grid">
                    {numeric("embeddingSeed", "Embedding seed", 194715)}
                    {numeric("vinaSeed", "Vina seed", 42)}
                  </div>
                  <p className="field-help">
                    Protocol: {config.protocol ?? "guided_local_cdk2_v1"} ·
                    target preparation:{" "}
                    {config.targetPreparationId ?? "cdk2_1h1p"}. Exported
                    records include resolved versions, seeds and the immutable
                    input specification.
                  </p>
                </details>
              </>
            )}
            {step === 2 && (
              <>
                <h2 tabIndex={-1}>Review your experiment</h2>
                <p className="section-description">
                  Each proposal keeps its input, outcome, coordinates and
                  checks.
                </p>
                <div className="review-summary">
                  <h3>{config.name}</h3>
                  <div className="flow-review-edit-actions" aria-label="Edit experiment settings">
                    <Button label="Edit property limits" variant="ghost" size="sm" onClick={() => setStep(1)} />
                    <Button label="Edit calculation budget" variant="ghost" size="sm" onClick={() => setStep(1)} />
                  </div>
                  <dl>
                    <div>
                      <dt>Target preparation</dt>
                      <dd>
                        {preset?.name ??
                          config.targetPreparationId ??
                          "Preparation not loaded"}
                      </dd>
                    </div>
                    <div>
                      <dt>Candidate source</dt>
                      <dd>
                        {config.source === "supplied"
                          ? `${entries.length} supplied candidates`
                          : `LibInvent · ${config.count} raw proposals`}
                      </dd>
                    </div>
                    <div>
                      <dt>Evaluation budget</dt>
                      <dd>
                        Up to {config.maxCandidates} unique candidates ·{" "}
                        {config.conformers} attempts each
                      </dd>
                    </div>
                    <div>
                      <dt>Property profile</dt>
                      <dd>
                        MW ≤ {config.maxMolecularWeight ?? 450} · cLogP ≤{" "}
                        {config.maxLogP} · rotors ≤{" "}
                        {config.maxRotatableBonds ?? 8}
                      </dd>
                    </div>
                    <div>
                      <dt>Admission window</dt>
                      <dd>{config.evaluationSeconds ?? 600} seconds</dd>
                    </div>
                    <div>
                      <dt>Protocol</dt>
                      <dd>{protocolLabel(config.protocol)}</dd>
                    </div>
                  </dl>
                  {config.source === "supplied" && (
                    <div className="review-input-preview">
                      <div>
                        <h4>Inputs to evaluate</h4>
                        <button
                          type="button"
                          className="text-link"
                          onClick={() => setStep(0)}
                        >
                          Edit candidates
                        </button>
                      </div>
                      <ul>
                        {entries.map((entry, index) => (
                          <li key={index}>{entry.name}</li>
                        ))}
                      </ul>
                      <p className="field-help">
                        Parsing, normalization and scope checks happen in the
                        worker. Inputs may be excluded before pose evaluation.
                      </p>
                    </div>
                  )}
                </div>
                <div className="info-block">
                  <Layers size={20} />
                  <p>
                    Inspect geometry checks and computed contacts in the pocket.
                    An improved score or contact is a hypothesis for review, not
                    experimental evidence of better binding.
                  </p>
                </div>
                {preset?.scope && <p className="field-help">{preset.scope}</p>}
                {preset?.limitations?.length ? (
                  <details className="setup-advanced">
                    <summary>Protocol scope and limitations</summary>
                    <ul>
                      {preset.limitations.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
                <details className="setup-advanced">
                  <summary>Inspect the exact request</summary>
                  <pre>{JSON.stringify(toRequest(config), null, 2)}</pre>
                </details>
                {!ready && (
                  <div className={w.demo ? "info-block" : "product-error"}>
                    {w.demo ? <Info size={18} aria-hidden="true" /> : <TriangleAlert size={18} aria-hidden="true" />}
                    <div>
                      {w.demo
                        ? "This is a recorded example. Start the local app to run your own experiments."
                        : !w.health.ready
                          ? "The local engine needs setup before this experiment can run."
                          : !preset
                            ? "Reference preparation metadata is unavailable. Return to Candidates and reload preparations."
                            : "The LibInvent environment needs setup before generation can run."}
                      {" "}<StudioLink to="/engine">Open engine settings</StudioLink>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
          <aside className="setup-context">
            <div className="setup-context-top">
              <span className="eyebrow">THE DESIGN QUESTION</span>
              <h2>Can a side group reach Asp86?</h2>
              <p className="flow-brief-preparation">{preset?.name ?? "CDK2 reference preparation"}</p>
              {preset && (
                <img
                  src={`/data/depictions/${preset?.parent.name === "NU6094" ? "1H1Q" : "1H1P"}.svg`}
                  alt={`${preset?.parent.name ?? "Parent"} reference molecular structure`}
                  onError={(e) => {
                    e.currentTarget.style.display = "none";
                  }}
                />
              )}
              <dl>
                <div>
                  <dt>Starting ligand</dt>
                  <dd>{preset?.parent.name ?? "Not loaded"}</dd>
                </div>
                <div>
                  <dt>Protein structure</dt>
                  <dd>{preset?.receptor_pdb_id ?? "—"}</dd>
                </div>
                <div>
                  <dt>Editable region</dt>
                  <dd>
                    {preset?.manifest.scaffold?.attachment_atom_name === "C20"
                      ? "Para carbon (C20)"
                      : preset
                        ? `${preset.manifest.scaffold?.attachment_atom_name ?? "N2"} side group`
                        : "—"}
                  </dd>
                </div>
              </dl>
            </div>
            <div className="setup-context-note">
              <LockKeyhole size={17} />
              <p>
                {preset?.manifest.scaffold?.retained_heavy_atoms
                  ? `${preset.manifest.scaffold.retained_heavy_atoms} parent heavy atoms stay intact. `
                  : "Parent atoms and bonds stay intact. "}
                The pose can adjust in the fixed protein pocket.
              </p>
            </div>
            <StudioLink className="text-link" to="/references/cdk2">
              Explore the reference study <ArrowRight size={15} />
            </StudioLink>
          </aside>
        </div>
        <footer className="setup-footer">
          <div>
            <span className="draft-saved">
              <Check size={14} />
              {saved ? "Draft saved on this device" : "Saving draft…"}
            </span>
            <span>Step {step + 1} of 3</span>
          </div>
          <div>
            {step > 0 && (
              <Button
                label="Back"
                variant="secondary"
                icon={<ArrowLeft size={16} />}
                onClick={() => {
                  setStep(step - 1);
                  setError("");
                }}
              />
            )}
            <Button
              className="setup-submit"
              label={
                w.submitting || launching
                  ? "Starting experiment…"
                  : step === 2
                    ? "Run experiment"
                    : "Continue"
              }
              type="submit"
              variant="primary"
              icon={<ArrowRight size={16} />}
              isDisabled={w.submitting || launching || (step === 2 && !ready)}
            />
          </div>
        </footer>
      </form>
    </section>
  );
}
