import { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Copy,
  RefreshCw,
  Server,
  TriangleAlert,
} from "lucide-react";
import { PageHeader, InlineError } from "./ProductUI";
import { StudioLink, useStudio } from "./StudioContext";
import { MolecularWorkspace } from "./WorkspacePage";
export function ReferencePage() {
  return (
    <section className="experiment-page reference-page">
      <header className="experiment-page-header">
        <nav className="breadcrumb" aria-label="Breadcrumb">
          <StudioLink to="/">Overview</StudioLink>
          <span>/</span>
          <span>References</span>
        </nav>
        <div className="experiment-title-row">
          <div>
            <h1>CDK2 reference study</h1>
            <p>
              Four observed structures. One preserved scaffold. Explore how the
              N2 side group changes its pocket contacts.
            </p>
          </div>
          <StudioLink className="primary-link" to="/experiments/new">
            Start CDK2 experiment <ArrowRight size={16} />
          </StudioLink>
        </div>
        <div className="reference-context">
          <span>NU2058 · NU6094 · NU6086 · NU6102</span>
          <a
            href="https://www.rcsb.org/structure/1H1P"
            target="_blank"
            rel="noreferrer"
          >
            Source structures on RCSB PDB <ArrowUpRight size={14} />
          </a>
        </div>
      </header>
      <MolecularWorkspace reference />
      <div className="reference-footnote">
        <p>
          These are experimentally observed crystal poses in their own receptor
          structures. They illustrate the design context; they are not the
          output of a live calculation.
        </p>
        <a className="text-link" href="/experiments?mode=demo">
          Open recorded generated example
          <ArrowRight size={15} />
        </a>
      </div>
    </section>
  );
}
export function EnginePage() {
  const w = useStudio();
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  const raw = w.health.raw as any;
  const checks = Array.isArray(raw?.checks) ? raw.checks : [];
  const runtime = raw?.worker?.health;
  const rows = [
    {
      name: "Local API",
      ok: w.health.connected,
      detail: w.health.connected
        ? "Connected through this app’s configured API."
        : w.health.detail || "The API is not connected.",
    },
    {
      name: "Calculation worker",
      ok: w.health.workerReady,
      detail: w.health.workerReady
        ? "A worker heartbeat is available."
        : "Start the local worker to claim queued calculations.",
    },
    {
      name: "Science environment",
      ok: w.health.ready,
      detail: w.health.ready
        ? "The configured runtime passed its readiness checks."
        : checks
            .filter((c: any) => !c.ok)
            .map((c: any) => c.message)
            .join(" ") || "Waiting for a verified worker runtime.",
    },
    {
      name: "LibInvent generator",
      optional: true,
      ok: w.health.generatorReady,
      detail: w.health.generatorReady
        ? "Generation runtime and model are ready."
        : "Optional for supplied candidates. Install the generator environment to propose variants.",
    },
  ];
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(
          {
            checkedAt: new Date().toISOString(),
            mode: w.demo ? "recorded" : "live",
            readiness: w.health,
          },
          null,
          2,
        ),
      );
      setCopied(true);
      setCopyError("");
    } catch {
      setCopyError(
        "Clipboard access was unavailable. You can select diagnostics below and copy them.",
      );
    }
  };
  return (
    <section className="product-page support-page">
      <PageHeader
        title="Local engine"
        description="Connection and runtime checks for calculations on this computer."
        actions={
          <button
            className="secondary-button"
            onClick={() => void w.refreshHealth()}
            disabled={w.demo}
          >
            <RefreshCw size={15} />
            Check again
          </button>
        }
      />
      {w.demo && (
        <div className="info-block">
          <p>
            You are viewing a recorded example.{" "}
            <a href="/engine">Open live mode</a> to connect to a local API.
          </p>
        </div>
      )}
      <section className="engine-status-list">
        {rows.map((row) => (
          <div key={row.name}>
            <span
              className={`engine-check ${!w.demo && row.ok ? "ready" : ""}`}
            >
              {!w.demo && row.ok ? <Check size={19} /> : <Server size={19} />}
            </span>
            <div>
              <h2>{row.name}</h2>
              <p>{w.demo ? "Not checked in recorded mode." : row.detail}</p>
            </div>
            <span
              className={`engine-state ${!w.demo && row.ok ? "ready" : ""}`}
            >
              {w.demo
                ? "Not checked"
                : w.health.loading
                  ? "Checking…"
                  : row.ok
                    ? "Ready"
                    : row.optional
                      ? "Optional"
                      : "Needs attention"}
            </span>
          </div>
        ))}
      </section>
      <div className="engine-actions">
        <button className="secondary-button" onClick={() => void copy()}>
          <Copy size={15} />
          {copied ? "Diagnostics copied" : "Copy diagnostics"}
        </button>
        {w.draft && (
          <StudioLink className="primary-link" to="/experiments/new">
            Return to draft
            <ArrowRight size={16} />
          </StudioLink>
        )}
      </div>
      {copyError && <InlineError message={copyError} />}
      <section className="help-section">
        <h2>Start the local app</h2>
        <p>
          Run these commands from the CapyChem checkout after installing the
          project dependencies described in the quick start.
        </p>
        <pre>
          <code>
            .venv/bin/python scripts/setup_science.py --python python3.11
            --with-generator{`\n`}.venv/bin/python scripts/dev.py
          </code>
        </pre>
        <p>
          The launcher starts a local PostgreSQL database, API, calculation
          worker and workspace. Supply your own database with{" "}
          <code>--database-url</code> if needed.
        </p>
        <a
          className="text-link"
          href="https://github.com/ogngnaoh/capychem#quick-start"
          target="_blank"
          rel="noreferrer"
        >
          Read the installation guide
          <ArrowUpRight size={14} />
        </a>
      </section>
      <details className="engine-diagnostics">
        <summary>Runtime diagnostics</summary>
        <pre>
          {JSON.stringify(
            raw ?? { connected: false, detail: w.health.detail },
            null,
            2,
          )}
        </pre>
      </details>
      <p className="field-help">
        Endpoint configuration is read from the app environment. This page does
        not modify your Python environments or install software.
      </p>
    </section>
  );
}
export function HelpPage() {
  return (
    <section className="product-page support-page">
      <PageHeader
        title="Help"
        description="A short guide to the molecular design workflow."
      />
      <nav className="help-contents" aria-label="Help sections">
        <a href={`${location.pathname}${location.search}#first-experiment`}>
          Your first experiment
        </a>
        <a href={`${location.pathname}${location.search}#evidence`}>
          Reading the evidence
        </a>
        <a href={`${location.pathname}${location.search}#protocol`}>
          How the protocol works
        </a>
        <a href={`${location.pathname}${location.search}#studies`}>
          Repeated runs
        </a>
        <a href={`${location.pathname}${location.search}#troubleshooting`}>
          Troubleshooting
        </a>
      </nav>
      <section className="help-section" id="first-experiment">
        <h2>Your first experiment</h2>
        <ol className="help-steps">
          <li>
            <strong>Inspect the reference study.</strong> See how four related
            ligands sit in experimentally observed CDK2 pockets. This gives
            context for the side-group design task.
          </li>
          <li>
            <strong>Start with the recommended preparation.</strong> Preserve
            the NU6094 parent and explore a side group toward Asp86 in receptor
            1H1S. Supply your own candidates or generate variants with
            LibInvent.
          </li>
          <li>
            <strong>Set a bounded calculation.</strong> Property limits screen
            proposals. Candidate and embedding budgets limit computation.
          </li>
          <li>
            <strong>Review the evidence.</strong> Select a candidate and an
            exact pose, inspect contacts and checks, then pin and annotate
            useful comparisons.
          </li>
          <li>
            <strong>Test what carries across runs.</strong> Pin candidates worth
            following up. Evaluate that shortlist across declared seeds in a
            study, or start a new round while keeping the original evidence.
          </li>
        </ol>
        <StudioLink className="text-link" to="/experiments/new">
          Create an experiment
          <ArrowRight size={15} />
        </StudioLink>
      </section>
      <section className="help-section" id="evidence">
        <h2>Reading the evidence</h2>
        <dl className="help-definitions">
          <div>
            <dt>Observed pose</dt>
            <dd>
              A ligand’s coordinates from an experimental crystal structure.
              Each reference uses its own observed protein context.
            </dd>
          </div>
          <div>
            <dt>Computed pose</dt>
            <dd>
              A proposed arrangement evaluated by this local protocol. Different
              prepared states may represent different stereochemical
              interpretations of the input.
            </dd>
          </div>
          <div>
            <dt>Geometry checks</dt>
            <dd>
              Checks for physically implausible arrangements, including
              molecular geometry and overlap with the protein.
            </dd>
          </div>
          <div>
            <dt>Polar contacts</dt>
            <dd>
              Contacts detected from geometric rules. They suggest interactions
              worth inspecting; they do not establish binding affinity.
            </dd>
          </div>
          <div>
            <dt>Vina score</dt>
            <dd>
              A model score for prioritizing poses within the same preparation
              and protocol. It is not a measured potency.
            </dd>
          </div>
          <div>
            <dt>Ready to inspect</dt>
            <dd>
              A pose passed the protocol’s review gate. It still requires
              interpretation and further validation.
            </dd>
          </div>
        </dl>
      </section>
      <section className="help-section" id="protocol">
        <h2>How the protocol works</h2>
        <p>
          The recommended CDK2 workflow preserves the NU6094 scaffold and grows
          a substituent from its para carbon in receptor 1H1S. The parent
          template is transferred from 1H1Q by protein alignment. The receptor
          was chosen from a known ligand complex, so this is a retrospective,
          receptor-informed workflow. Legacy N2 experiments retain their
          original NU2058 / 1H1P preparation. The declared hypothesis is to
          explore a polar contact near Asp86 while retaining a plausible
          hinge-local pose.
        </p>
        <div className="protocol-flow">
          <span>Supplied series or LibInvent</span>
          <ArrowRight size={18} />
          <span>RDKit preparation & screening</span>
          <ArrowRight size={18} />
          <span>Pose refinement & scoring</span>
          <ArrowRight size={18} />
          <span>Geometry & contact evidence</span>
        </div>
        <p>
          Every input stays in the record, including invalid structures,
          duplicates, exclusions and candidates deferred by budget. Completion
          and scientific outcome are reported separately.
        </p>
        <p>
          CapyChem currently supports the curated CDK2 preparation. It does not
          accept arbitrary proteins or claim that a generated molecule will be
          experimentally active.
        </p>
      </section>
      <section className="help-section" id="studies">
        <h2>Compare repeated runs</h2>
        <p>
          An experiment evaluates one candidate set with one set of random
          seeds. A study repeats the same supplied molecules and fixed protocol
          across seeds declared before the calculations start.
        </p>
        <p>
          The matrix shows how often each candidate has a pose ready to inspect,
          how often that ready pose also has an Asp86 contact, and its score
          range. Open a cell to inspect the exact run and selected pose. Missing
          or failed evaluations remain visible; these counts are not binding
          probabilities or a ranking of clinical promise.
        </p>
        <StudioLink className="text-link" to="/studies/new">
          Plan a study <ArrowRight size={15} />
        </StudioLink>
      </section>
      <section className="help-section" id="troubleshooting">
        <h2>Troubleshooting</h2>
        <details>
          <summary>The API or worker is unavailable</summary>
          <p>
            Check Local engine. Already loaded evidence stays visible with a
            connection warning; new jobs require the live API. Saved drafts
            remain on this device.
          </p>
        </details>
        <details>
          <summary>An experiment has no usable poses</summary>
          <p>
            Open Activity and inspect exclusions, geometry failures, embedding
            errors and attempt details. Use New round to adjust the candidate
            set or budget without changing the original record.
          </p>
        </details>
        <details>
          <summary>Another tab changed a pin or note</summary>
          <p>
            Decisions have revisions. If an edit conflicts, CapyChem shows the
            newer saved state and retains your note draft so you can review and
            save deliberately.
          </p>
        </details>
        <details>
          <summary>A run was cancelled or interrupted</summary>
          <p>
            Cancellation takes effect at a safe checkpoint. A reclaimed job
            creates another execution attempt; previous attempt artifacts remain
            available in Activity.
          </p>
        </details>
        <StudioLink className="text-link" to="/engine">
          Check the local engine
          <ArrowRight size={15} />
        </StudioLink>
      </section>
      <section className="help-section">
        <h2>Open-source components and references</h2>
        <div className="source-links">
          <a
            href="https://github.com/MolecularAI/REINVENT4"
            target="_blank"
            rel="noreferrer"
          >
            REINVENT / LibInvent
            <ArrowUpRight size={14} />
          </a>
          <a href="https://www.rdkit.org/" target="_blank" rel="noreferrer">
            RDKit
            <ArrowUpRight size={14} />
          </a>
          <a
            href="https://github.com/ccsb-scripps/AutoDock-Vina"
            target="_blank"
            rel="noreferrer"
          >
            AutoDock Vina
            <ArrowUpRight size={14} />
          </a>
          <a
            href="https://github.com/maabuu/posebusters"
            target="_blank"
            rel="noreferrer"
          >
            PoseBusters
            <ArrowUpRight size={14} />
          </a>
          <a
            href="https://www.rcsb.org/structure/1H1P"
            target="_blank"
            rel="noreferrer"
          >
            RCSB PDB · 1H1P
            <ArrowUpRight size={14} />
          </a>
          <a href="/THIRD_PARTY_NOTICES.txt" target="_blank" rel="noreferrer">
            Third-party notices
            <ArrowUpRight size={14} />
          </a>
        </div>
      </section>
    </section>
  );
}
