import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@astryxdesign/core/Button";
import { TextInput } from "@astryxdesign/core/TextInput";
import { ArrowLeft, ArrowRight, Check, Plus, Trash2 } from "lucide-react";
import {
  useStudio,
  StudioLink,
  useStudioNavigate,
  protocolLabel,
} from "./StudioContext";
import {
  DEFAULT_EXPERIMENT,
  parseCandidates,
  type ExperimentConfig,
} from "./experimentConfig";
import { fromSpec, toRequest } from "./useWorkspace";
import { request } from "./api";
import { InlineError, LoadingState, PageHeader } from "./ProductUI";
import {
  DEFAULT_STUDY_SEEDS,
  readStudyDraft,
  saveStudyDraft,
  clearStudyDraft,
  type SeedPair,
  type Study,
} from "./studyModel";
import "./study.css";

const STEPS = ["Candidates", "Rules & seeds", "Review"];
const LIMITS = [
  ["maxMolecularWeight", "Maximum molecular weight", 450, 100, 1000, 1],
  ["maxLogP", "Maximum calculated logP", 4.5, -5, 10, 0.1],
  ["maxRotatableBonds", "Maximum rotatable bonds", 8, 0, 30, 1],
  ["maxCandidates", "Maximum candidates per run", 8, 1, 64, 1],
  ["conformers", "Embedding attempts per candidate", 16, 1, 32, 1],
  ["evaluationSeconds", "Admission window per run (seconds)", 300, 10, 3600, 1],
] as const;
const validSeed = (n: number) =>
  Number.isInteger(n) && n >= 0 && n <= 2147483000;
const pendingSubmissions = new Map<string, string>();

async function studySubmissionKey(body: string) {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(body),
  );
  const hash = Array.from(new Uint8Array(bytes), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
  const storage = `capychem-study-submit-v1-${hash}`;
  let key = pendingSubmissions.get(storage) || crypto.randomUUID();
  try {
    key = sessionStorage.getItem(storage) || key;
    sessionStorage.setItem(storage, key);
  } catch {
    /* In-memory keys preserve retries when browser storage is unavailable. */
  }
  pendingSubmissions.set(storage, key);
  return { key, storage };
}

export function StudySetupPage() {
  const w = useStudio(),
    navigate = useStudioNavigate();
  const [draft] = useState(() => readStudyDraft(w.demo));
  const [config, setConfig] = useState<ExperimentConfig>(
    () =>
      draft?.config ?? {
        ...DEFAULT_EXPERIMENT,
        name: "CDK2 · repeat-seed study",
        source: "supplied",
      },
  );
  const [seeds, setSeeds] = useState<SeedPair[]>(
    () => draft?.seeds ?? DEFAULT_STUDY_SEEDS.map((s) => ({ ...s })),
  );
  const [step, setStep] = useState(draft?.step ?? 0);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [persisted, setPersisted] = useState(false);
  const lock = useRef(false),
    initialized = useRef(Boolean(draft)),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (initialized.current || !w.presets.length) return;
    const p = w.presets.find((p) => p.recommended) ?? w.presets[0];
    initialized.current = true;
    setConfig({
      ...fromSpec(p.default_spec),
      source: "supplied",
      name: "CDK2 · repeat-seed study",
      evaluationSeconds: 300,
    });
  }, [w.presets]);
  useEffect(() => {
    if (initialized.current)
      setPersisted(
        saveStudyDraft(w.demo, {
          config,
          seeds,
          step,
          sourceName: draft?.sourceName,
        }),
      );
  }, [config, seeds, step, w.demo, draft?.sourceName]);
  useEffect(() => {
    window.scrollTo(0, 0);
    document
      .querySelector<HTMLElement>(".study-setup h2")
      ?.focus({ preventScroll: true });
  }, [step]);
  const preset = w.presets.find((p) => p.id === config.targetPreparationId);
  const entries = parseCandidates(config.suppliedText);
  const inputError = !config.name.trim()
    ? "Give the study a name."
    : config.name.length > 160
      ? "Keep the study name within 160 characters."
      : entries.length < 1 || entries.length > 128
        ? "Supply between 1 and 128 candidates."
        : entries.some((c) => c.smiles.length > 4096 || c.name.length > 160)
          ? "Use at most 4096 characters per SMILES and 160 per name."
          : "";
  const badLimit = LIMITS.find(([key, , fallback, min, max, increment]) => {
    const value = config[key] ?? fallback;
    return (
      !Number.isFinite(value) ||
      value < min ||
      value > max ||
      (increment === 1 && !Number.isInteger(value))
    );
  });
  const seedsError =
    seeds.length < 2 || seeds.length > 8
      ? "Use between 2 and 8 seed pairs."
      : seeds.some((s) => !validSeed(s.embedding) || !validSeed(s.vina))
        ? "Seeds must be whole numbers from 0 to 2147483000."
        : new Set(seeds.map((s) => `${s.embedding}:${s.vina}`)).size !==
            seeds.length
          ? "Each embedding and Vina seed pair must be different."
          : "";
  const base = toRequest({
    ...config,
    source: "supplied",
    name: config.name.trim(),
  });
  const { label: _label, seeds: _seeds, ...baseSpec } = base;
  const payload = {
    label: config.name.trim(),
    base_spec: baseSpec,
    seed_pairs: seeds,
  };
  const ready = !w.demo && w.health.ready && !!preset && !w.presetsLoading;
  const update = (patch: Partial<ExperimentConfig>) => {
    initialized.current = true;
    setConfig((c) => ({ ...c, ...patch }));
  };
  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (lock.current) return;
    if (inputError) {
      setError(inputError);
      setStep(0);
      return;
    }
    if (step > 0 && (badLimit || seedsError)) {
      setError(seedsError || `Check ${badLimit?.[1].toLowerCase()}.`);
      setStep(1);
      return;
    }
    setError("");
    if (step < 2) {
      setStep(step + 1);
      return;
    }
    if (!ready) return;
    lock.current = true;
    setSubmitting(true);
    let succeeded = false;
    try {
      const body = JSON.stringify(payload);
      const token = await studySubmissionKey(body);
      const study = await request<Study>("/studies", {
        method: "POST",
        body,
        headers: { "Idempotency-Key": token.key },
      });
      succeeded = true;
      pendingSubmissions.delete(token.storage);
      try {
        sessionStorage.removeItem(token.storage);
      } catch {
        /* Submission is already durable. */
      }
      clearStudyDraft(w.demo);
      if (alive.current) navigate(`/studies/${study.id}`);
    } catch (e) {
      if (alive.current)
        setError(
          e instanceof Error ? e.message : "The study could not be started.",
        );
    } finally {
      // Navigation can commit after another click arrives. Keep a successful
      // form locked until it unmounts; only failed requests are retryable here.
      if (!succeeded) {
        lock.current = false;
        if (alive.current) setSubmitting(false);
      }
    }
  };
  if (w.presetsLoading && !draft)
    return <LoadingState label="Loading study preparation…" />;
  return (
    <section className="product-page study-setup flow-v5">
      <PageHeader
        title="New study"
        description="Test the same molecular series across several sampling seeds."
        actions={
          <StudioLink className="text-link" to="/studies">
            Save and exit <ArrowRight size={16} />
          </StudioLink>
        }
      />
      <ol className="setup-steps" aria-label="Study setup">
        {STEPS.map((name, i) => (
          <li
            key={name}
            className={step === i ? "current" : step > i ? "done" : ""}
          >
            <button
              type="button"
              disabled={i > step || submitting}
              aria-current={i === step ? "step" : undefined}
              onClick={() => {
                setError("");
                setStep(i);
              }}
            >
              <span>{step > i ? <Check size={14} /> : i + 1}</span>
              {name}
            </button>
          </li>
        ))}
      </ol>
      {w.presetsError && (
        <InlineError message={w.presetsError} onRetry={w.refreshPresets} />
      )}
      <form onSubmit={onSubmit} className="study-form">
        <div className="study-form-main">
          {config.parentId && (
            <p className="study-source">
              Shortlist from{" "}
              <StudioLink to={`/experiments/${config.parentId}`}>
                {draft?.sourceName || "source experiment"}
              </StudioLink>
              . Unchanged molecules retain their source links.
            </p>
          )}
          {step === 0 && (
            <>
              <h2 tabIndex={-1}>Choose a molecular series</h2>
              <p className="section-description">
                Supply candidates with the supported parent scaffold. Each run
                evaluates the same inputs independently.
              </p>
              <TextInput
                label="Study name"
                value={config.name}
                onChange={(value) => update({ name: value.slice(0, 160) })}
                width="100%"
              />
              <label className="study-field">
                Reference preparation
                <select
                  value={config.targetPreparationId || ""}
                  onChange={(e) => {
                    const p = w.presets.find((p) => p.id === e.target.value);
                    if (p)
                      update({
                        ...fromSpec(p.default_spec),
                        name: config.name,
                        source: "supplied",
                        parentId: undefined,
                        originCandidates: undefined,
                      });
                  }}
                >
                  {w.presets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                      {p.recommended
                        ? " · Recommended"
                        : " · Historical comparison"}
                    </option>
                  ))}
                </select>
              </label>
              <div className="study-field-heading">
                <label htmlFor="study-candidates">Candidates</label>
                <Button
                  label="Use reference series"
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    preset &&
                    update({
                      suppliedText: preset.reference_candidates
                        .map((c) => `${c.smiles} ${c.name}`)
                        .join("\n"),
                      originCandidates: undefined,
                    })
                  }
                />
              </div>
              <div className="flow-input-preview" aria-label="Supplied study candidate names">
                <div>
                  <strong>Inputs in every run</strong>
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
                id="study-candidates"
                rows={8}
                value={config.suppliedText}
                spellCheck={false}
                onChange={(e) => update({ suppliedText: e.target.value })}
              />
              <p className="field-help">
                One SMILES and optional name per line. {entries.length} inputs.
                Invalid and excluded inputs remain visible with their reason.
              </p>
              <p className="field-help">
                To generate molecules first,{" "}
                <StudioLink className="text-link" to="/experiments/new">
                  start an experiment
                </StudioLink>
                , then evaluate its pinned shortlist here.
              </p>
            </>
          )}
          {step === 1 && (
            <>
              <h2 tabIndex={-1}>Keep the rules fixed. Vary the sampling.</h2>
              <p className="section-description">
                A seed changes the starting arrangements and local search. These
                runs share one preparation and objective.
              </p>
              <div className="study-number-grid">
                {LIMITS.map(([key, name, fallback, min, max, increment]) => (
                  <label className="study-field" key={key}>
                    {name}
                    <input
                      type="number"
                      min={min}
                      max={max}
                      step={increment}
                      value={
                        Number.isFinite(config[key] ?? fallback)
                          ? (config[key] ?? fallback)
                          : ""
                      }
                      onChange={(e) =>
                        update({
                          [key]:
                            e.target.value === ""
                              ? NaN
                              : Number(e.target.value),
                        })
                      }
                    />
                  </label>
                ))}
              </div>
              <p className="field-help">
                Formal charge is fixed at neutral. Embedding attempts try
                starting 3D arrangements; fewer distinct poses may succeed.
              </p>
              <div className="study-field-heading">
                <h3>Sampling seeds</h3>
                <button
                  className="text-link"
                  type="button"
                  disabled={seeds.length >= 8}
                  onClick={() =>
                    setSeeds((s) => [
                      ...s,
                      {
                        embedding: Math.max(...s.map((x) => x.embedding)) + 101,
                        vina: Math.max(...s.map((x) => x.vina)) + 1,
                      },
                    ])
                  }
                >
                  <Plus size={15} />
                  Add run
                </button>
              </div>
              <div className="study-seed-head">
                <span>Run</span>
                <span>Embedding seed</span>
                <span>Vina seed</span>
                <span />
              </div>
              {seeds.map((seed, i) => (
                <div className="study-seed-row" key={i}>
                  <strong>{i + 1}</strong>
                  {(["embedding", "vina"] as const).map((kind) => (
                    <input
                      key={kind}
                      type="number"
                      aria-label={`Run ${i + 1} ${kind} seed`}
                      min={0}
                      max={2147483000}
                      step={1}
                      value={Number.isFinite(seed[kind]) ? seed[kind] : ""}
                      onChange={(e) =>
                        setSeeds((s) =>
                          s.map((v, n) =>
                            n === i
                              ? {
                                  ...v,
                                  [kind]:
                                    e.target.value === ""
                                      ? NaN
                                      : Number(e.target.value),
                                }
                              : v,
                          ),
                        )
                      }
                    />
                  ))}
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Remove run ${i + 1}`}
                    disabled={seeds.length <= 2}
                    onClick={() => setSeeds((s) => s.filter((_, n) => n !== i))}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
              <p className="field-help">
                Use 2–8 distinct pairs. Repeated seeds would repeat the same
                sampling rather than test sensitivity.
              </p>
            </>
          )}
          {step === 2 && (
            <>
              <h2 tabIndex={-1}>Review your study</h2>
              <p className="section-description">
                The study and all run specifications are saved before the worker
                starts.
              </p>
              <div className="study-review">
                <h3>{config.name}</h3>
                <div className="flow-review-edit-actions" aria-label="Edit study settings">
                  <Button label="Edit rules and budget" variant="ghost" size="sm" onClick={() => setStep(1)} />
                  <Button label="Edit sampling seeds" variant="ghost" size="sm" onClick={() => setStep(1)} />
                </div>
                <dl>
                  <div>
                    <dt>Preparation</dt>
                    <dd>{preset?.name}</dd>
                  </div>
                  <div>
                    <dt>Plan</dt>
                    <dd>
                      {entries.length} inputs × {seeds.length} runs
                    </dd>
                  </div>
                  <div>
                    <dt>Budget</dt>
                    <dd>
                      Up to{" "}
                      {Math.min(entries.length, config.maxCandidates) *
                        seeds.length}{" "}
                      candidate evaluations · {config.conformers} embedding
                      attempts each
                    </dd>
                  </div>
                  <div>
                    <dt>Profile</dt>
                    <dd>
                      MW ≤ {config.maxMolecularWeight ?? 450} · cLogP ≤{" "}
                      {config.maxLogP} · rotors ≤{" "}
                      {config.maxRotatableBonds ?? 8}
                    </dd>
                  </div>
                  <div>
                    <dt>Admission window</dt>
                    <dd>{config.evaluationSeconds ?? 600} seconds per run</dd>
                  </div>
                  <div>
                    <dt>Protocol</dt>
                    <dd>{protocolLabel(config.protocol)}</dd>
                  </div>
                </dl>
                <div className="study-field-heading">
                  <h3>Inputs to evaluate</h3>
                  <button
                    type="button"
                    className="text-link"
                    onClick={() => setStep(0)}
                  >
                    Edit candidates
                  </button>
                </div>
                <ul>
                  {entries.map((c, i) => (
                    <li key={i}>{c.name}</li>
                  ))}
                </ul>
                <p className="field-help">
                  Seed pairs:{" "}
                  {seeds.map((s) => `${s.embedding} / ${s.vina}`).join(" · ")}
                </p>
              </div>
              <p className="study-interpretation">
                The comparison shows how often selected poses pass checks and
                make the proposed contact. Counts across seeds are not binding
                probabilities or measured affinity.
              </p>
              <details className="study-disclosure">
                <summary>Inspect the exact request</summary>
                <pre>{JSON.stringify(payload, null, 2)}</pre>
              </details>
            </>
          )}
          {error && <InlineError message={error} />}
          <div className="study-form-footer">
            <span className="field-help">
              {persisted
                ? "Draft saved on this device"
                : "Draft kept in this session"}{" "}
              · Step {step + 1} of 3
            </span>
            <div>
              {step > 0 && (
                <Button
                  label="Back"
                  variant="secondary"
                  icon={<ArrowLeft size={15} />}
                  isDisabled={submitting}
                  onClick={() => setStep((s) => s - 1)}
                />
              )}
              <Button
                label={submitting ? "Starting study…" : step === 2 ? `Run ${seeds.length} experiments` : "Continue"}
                variant="primary"
                type="submit"
                isDisabled={submitting || (step === 2 && !ready)}
                endContent={<ArrowRight size={16} />}
              />
            </div>
          </div>
        </div>
        <aside className="study-brief">
          <span className="eyebrow">THE REPEATABILITY QUESTION</span>
          <h2>One question, repeated.</h2>
          <p>
            Does the proposed contact remain when the same molecule starts from
            different arrangements?
          </p>
          <dl>
            <div>
              <dt>Target</dt>
              <dd>{preset?.receptor_pdb_id || "CDK2"}</dd>
            </div>
            <div>
              <dt>Parent</dt>
              <dd>{preset?.parent.name || "—"}</dd>
            </div>
            <div>
              <dt>Runs planned</dt>
              <dd>{seeds.length}</dd>
            </div>
            <div>
              <dt>Inputs per run</dt>
              <dd>{entries.length}</dd>
            </div>
          </dl>
          <p>{preset?.scope || preset?.description}</p>
          <details>
            <summary>Protocol assumptions</summary>
            <ul>
              {preset?.limitations?.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </details>
          {(w.demo || !w.health.ready) && (
            <div className="study-engine-note">
              <strong>
                {w.demo ? "Recorded example" : "Local engine required"}
              </strong>
              <p>
                {w.demo
                  ? "This example launches no calculations. Run CapyChem locally to execute this study."
                  : "You can prepare this study now. Start the local engine to run it."}
              </p>
              <StudioLink className="text-link" to="/engine">
                Open engine setup <ArrowRight size={14} />
              </StudioLink>
            </div>
          )}
        </aside>
      </form>
    </section>
  );
}
