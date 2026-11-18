import { lazy, Suspense, useState } from "react";
import { Badge } from "@astryxdesign/core/Badge";
import { ArrowRight, ArrowUpRight, Plus, FlaskConical } from "lucide-react";
import { StudioLink, useStudio } from "./StudioContext";
import { StudioActionLink } from "./StudioActionLink";
import {
  EmptyState,
  LoadingState,
  PageHeader,
  StatusLabel,
  InlineError,
  readableDate,
} from "./ProductUI";
import { isActive } from "./experimentModel";
import { useStudies } from "./useStudies";
const MolecularViewport = lazy(() => import("./MolecularViewport"));

export function OverviewPage() {
  const w = useStudio();
  const [collection, setCollection] = useState<"experiments" | "studies">(
    "experiments",
  );
  const references = w.structures.filter((s) => s.origin === "observed");
  const recent = w.runs.slice(0, 4);
  return (
    <section className="product-page overview-page flow-v5">
      <PageHeader title="Overview" />
      <div className="overview-hero">
        <div className="overview-intro">
          <span className="eyebrow">MOLECULAR DESIGN WORKSPACE</span>
          <h2>Design and evaluate molecular variants.</h2>
          <p>
            Explore CDK2 side groups with local models. Inspect each pose,
            compare repeated runs, and keep the evidence.
          </p>
          <div className="overview-actions">
            <StudioActionLink to="/experiments/new" label="New experiment" variant="primary" icon={<Plus size={18} />} />
            <StudioLink className="text-link" to="/references/cdk2">
              Inspect reference <ArrowRight size={17} />
            </StudioLink>
          </div>
          <div className="overview-scope"><Badge variant="neutral" label="Curated CDK2 workflow" /><span>{w.demo ? "Recorded example" : "Runs on your computer"}</span></div>
          {w.draft && (
            <StudioLink className="resume-draft" to="/experiments/new">
              Continue setup <span>{w.draft.config.name}</span>
              <ArrowRight size={15} />
            </StudioLink>
          )}
        </div>
        <div className="overview-media">
          <div className="overview-molecular-view">
            {references.length ? (
              <Suspense
                fallback={<LoadingState label="Loading molecular view…" />}
              >
                <MolecularViewport structures={references} structureId="1H1S" />
              </Suspense>
            ) : w.loadError ? (
              <InlineError
                message={w.loadError}
                onRetry={w.refreshReferences}
              />
            ) : (
              <LoadingState label="Loading reference coordinates…" />
            )}
          </div>
          <StudioLink
            className="overview-media-caption"
            to="/references/cdk2?candidate=1H1S"
          >
            <span>NU6102 · observed structure 1H1S</span>
            <span>
              Inspect the binding pocket <ArrowUpRight size={16} />
            </span>
          </StudioLink>
        </div>
      </div>
      <ol className="flow-workflow-strip" aria-label="Molecular design workflow">
        <li><span>01</span><div><strong>Evaluate a series</strong><p>Supply candidates or generate side groups.</p></div></li>
        <li><span>02</span><div><strong>Inspect the evidence</strong><p>Review poses, geometry and pocket contacts.</p></div></li>
        <li><span>03</span><div><strong>Compare across seeds</strong><p>Repeat a shortlist and keep each result.</p></div></li>
      </ol>
      <section className="overview-recent">
        <div className="section-heading">
          <h2>Recent work</h2>
          <StudioLink
            className="text-link"
            to={collection === "experiments" ? "/experiments" : "/studies"}
          >
            View all <ArrowRight size={16} />
          </StudioLink>
        </div>
        <div
          className="collection-tabs"
          role="tablist"
          aria-label="Recent work"
        >
          <button
            id="recent-experiments-tab"
            role="tab"
            aria-selected={collection === "experiments"}
            aria-controls="recent-work-panel"
            onClick={() => setCollection("experiments")}
          >
            Experiments
          </button>
          <button
            id="recent-studies-tab"
            role="tab"
            aria-selected={collection === "studies"}
            aria-controls="recent-work-panel"
            onClick={() => setCollection("studies")}
          >
            Studies
          </button>
        </div>
        <div
          id="recent-work-panel"
          role="tabpanel"
          aria-labelledby={`recent-${collection}-tab`}
        >
          {collection === "studies" ? (
            <RecentStudies demo={w.demo} />
          ) : w.loading ? (
            <LoadingState label="Loading experiments…" />
          ) : recent.length ? (
            <div className="product-table-wrap">
              <table className="product-table recent-table">
                <thead>
                  <tr>
                    <th>Experiment</th>
                    <th>Status</th>
                    <th>Candidates</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((run) => (
                    <tr key={run.id}>
                      <td>
                        <StudioLink
                          to={`/experiments/${run.id}${isActive(run) ? "/activity" : ""}`}
                        >
                          {run.name}
                        </StudioLink>
                        <small>
                          {w.presets.find(
                            (p) => p.id === run.config.targetPreparationId,
                          )?.name ??
                            run.config.targetPreparationId ??
                            "CDK2 · 1H1P"}
                        </small>
                      </td>
                      <td>
                        <StatusLabel status={run.status} />
                      </td>
                      <td>
                        {run.candidateCount || isActive(run)
                          ? run.candidateCount
                          : "0"}
                      </td>
                      <td>
                        <time dateTime={run.createdAt}>
                          {readableDate(run.createdAt)}
                        </time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={
                w.health.connected || w.demo
                  ? "No experiments yet"
                  : "Your experiments will appear here"
              }
              body={
                w.health.connected || w.demo
                  ? "Start with the CDK2 reference series or bring candidates that share its parent scaffold."
                  : "Connect the local API to access saved work. You can inspect the reference study now."
              }
              icon={<FlaskConical size={28} />}
              action={
                <StudioLink
                  className="secondary-button"
                  to={
                    w.health.connected || w.demo
                      ? "/experiments/new"
                      : "/engine"
                  }
                >
                  {w.health.connected || w.demo
                    ? "Create an experiment"
                    : "Open engine settings"}
                  <ArrowRight size={15} />
                </StudioLink>
              }
            />
          )}
        </div>
        <div className="overview-next-step">
          <p>
            Start with supplied molecules or generate variants. Use a study to
            compare the same candidates across declared seeds.
          </p>
          <StudioLink className="text-link" to="/studies/new">
            Plan a study <ArrowRight size={16} />
          </StudioLink>
        </div>
        <p className="local-storage-note">
          {w.demo
            ? "This recorded example preserves the original inputs, coordinates and evidence."
            : "Calculations and results stay on this computer."}
        </p>
      </section>
      {!w.demo && !w.health.loading && !w.health.ready && (
        <div className="overview-engine-notice">
          <div>
            <h3>Set up your local engine</h3>
            <p>
              You can inspect the reference study now. Connect the engine to run
              calculations.
            </p>
          </div>
          <StudioLink className="text-link" to="/engine">
            Open engine settings
            <ArrowRight size={16} />
          </StudioLink>
        </div>
      )}
    </section>
  );
}

function RecentStudies({ demo }: { demo: boolean }) {
  const { items, loading, error, refresh } = useStudies(demo);
  if (loading) return <LoadingState label="Loading studies…" />;
  if (error)
    return (
      <InlineError
        message={`Studies could not be loaded. ${error}`}
        onRetry={refresh}
      />
    );
  if (!items.length)
    return (
      <EmptyState
        title="Compare your next round across seeds"
        body="A study evaluates the same supplied candidates in repeated runs, keeping every result linked to its exact pose."
        action={
          <StudioLink className="secondary-button" to="/studies/new">
            Plan a study <ArrowRight size={15} />
          </StudioLink>
        }
      />
    );
  return (
    <div className="product-table-wrap">
      <table className="product-table recent-table">
        <thead>
          <tr>
            <th>Study</th>
            <th>Status</th>
            <th>Runs</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 4).map((study) => (
            <tr key={study.id}>
              <td>
                <StudioLink to={`/studies/${study.id}`}>
                  {study.label}
                </StudioLink>
                <small>
                  Same supplied series · {study.seed_pairs.length} declared
                  seeds
                </small>
              </td>
              <td>
                <StatusLabel status={study.status} />
              </td>
              <td>{study.members.length}</td>
              <td>
                <time dateTime={study.created_at}>
                  {readableDate(study.created_at)}
                </time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
