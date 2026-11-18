import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Button } from "@astryxdesign/core/Button";
import {
  Plus,
  ArrowRight,
  MoreHorizontal,
  Download,
  GitBranch,
  Activity,
} from "lucide-react";
import { request } from "./api";
import { normalizeRun } from "./useWorkspace";
import { type ExperimentRun, isActive } from "./experimentModel";
import { StudioLink, useStudio } from "./StudioContext";
import { CollectionTabs, CollectionToolbar } from "./CollectionToolbar";
import { StudioActionLink } from "./StudioActionLink";
import {
  PageHeader,
  StatusLabel,
  EmptyState,
  InlineError,
  LoadingState,
  readableDate,
  exportRecord,
  statusNames,
} from "./ProductUI";

export function ExperimentIndexPage() {
  const w = useStudio();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") || "";
  const status = params.get("status") || "";
  const cursor = params.get("cursor") || "";
  const [items, setItems] = useState<ExperimentRun[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (w.demo) {
      setItems(
        w.runs.filter(
          (r) =>
            (!status || r.status === status) &&
            `${r.name} ${r.id}`.toLowerCase().includes(query.toLowerCase()),
        ),
      );
      setNextCursor(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(items.length === 0);
    const timer = setTimeout(() => {
      const search = new URLSearchParams({ limit: "20" });
      if (query) search.set("q", query);
      if (status) search.set("status", status);
      if (cursor) search.set("cursor", cursor);
      request<{
        items: Record<string, unknown>[];
        next_cursor?: string;
        has_more?: boolean;
      }>(`/experiments?${search}`, { signal: controller.signal })
        .then((data) => {
          setItems(data.items.map(normalizeRun));
          setNextCursor(data.has_more ? (data.next_cursor ?? null) : null);
          setError("");
          setLoading(false);
        })
        .catch((e) => {
          if (!controller.signal.aborted) {
            setError(e.message);
            setLoading(false);
          }
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, status, cursor, retry, w.demo, w.demo ? w.runs : undefined]);
  useEffect(() => {
    if (w.demo) return;
    const timer = setInterval(
      () => {
        if (document.visibilityState === "visible") setRetry((n) => n + 1);
      },
      items.some(isActive) ? 4000 : 15000,
    );
    return () => clearInterval(timer);
  }, [w.demo, items.some(isActive)]);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("cursor");
    setParams(next, { replace: true });
  }
  const clear = () => {
    const next = new URLSearchParams();
    if (w.demo) next.set("mode", "demo");
    setParams(next);
  };
  return (
    <section className="product-page flow-v5 collection-page">
      <PageHeader
        title="Experiments"
        description="Your design rounds, results and decisions."
        actions={
          <StudioActionLink to="/experiments/new" label="New experiment" variant="primary" icon={<Plus size={17} />} />
        }
      />
      <CollectionTabs selected="experiments" />
      <CollectionToolbar label="Search experiments" placeholder="Search by name or experiment ID" query={query} onQuery={(value) => filter("q", value)}>
        <label className="status-filter">
          <span className="sr-only">Experiment status</span>
          <select
            aria-label="Experiment status"
            value={status}
            onChange={(e) => filter("status", e.target.value)}
          >
            <option value="">All statuses</option>
            {Object.entries(statusNames).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {(query || status) && (
          <Button label="Clear filters" variant="ghost" size="sm" onClick={clear} />
        )}
      </CollectionToolbar>
      <p className="flow-collection-context">A design round keeps its inputs, poses and review decisions together.</p>
      {items.length > 0 && (
        <p className="table-scroll-hint">
          Scroll sideways for source, dates and actions.
        </p>
      )}
      {error && (
        <InlineError
          message={`Experiments could not be loaded. ${error}`}
          onRetry={() => setRetry((n) => n + 1)}
        />
      )}
      {loading ? (
        <LoadingState label="Loading experiments…" />
      ) : !items.length && !error ? (
        <EmptyState
          title={
            query || status
              ? "No matching experiments"
              : "Your first experiment starts here"
          }
          body={
            query || status
              ? "Try another name or clear the filters."
              : "Evaluate candidates you provide, or generate side-group variants with LibInvent."
          }
          action={
            query || status ? (
              <button className="secondary-button" onClick={clear}>
                Clear filters
              </button>
            ) : (
              <StudioActionLink to="/experiments/new" label="New experiment" variant="primary" icon={<Plus size={16} />} />
            )
          }
        />
      ) : (
        items.length > 0 && (
          <div className="product-table-wrap">
            <table className="product-table experiment-index-table">
              <thead>
                <tr>
                  <th>Experiment</th>
                  <th>Status</th>
                  <th>Source</th>
                  <th>Candidates</th>
                  <th>Created</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <StudioLink
                        className="experiment-name-link"
                        to={`/experiments/${run.id}${isActive(run) ? "/activity" : ""}`}
                      >
                        {run.name}
                      </StudioLink>
                      <small>
                        {w.presets.find(
                          (p) => p.id === run.config.targetPreparationId,
                        )?.name ??
                          run.config.targetPreparationId ??
                          "CDK2 · N2 exploration"}
                        {run.parentId && (
                          <>
                            {" "}
                            · From{" "}
                            <StudioLink to={`/experiments/${run.parentId}`}>
                              {w.runs.find((p) => p.id === run.parentId)
                                ?.name ?? run.parentId.slice(0, 8)}
                            </StudioLink>
                          </>
                        )}
                      </small>
                    </td>
                    <td>
                      <StatusLabel status={run.status} />
                    </td>
                    <td>
                      {run.config.source === "libinvent"
                        ? "LibInvent"
                        : "Supplied"}
                    </td>
                    <td>{run.candidateCount}</td>
                    <td className="table-date">
                      {readableDate(run.createdAt)}
                    </td>
                    <td>
                      <details className="row-actions">
                        <summary aria-label={`Actions for ${run.name}`}>
                          <MoreHorizontal size={19} />
                        </summary>
                        <div>
                          <StudioLink to={`/experiments/${run.id}`}>
                            <ArrowRight size={14} />
                            Open experiment
                          </StudioLink>
                          <StudioLink to={`/experiments/${run.id}/activity`}>
                            <Activity size={14} />
                            View activity
                          </StudioLink>
                          <StudioLink to={`/experiments/new?from=${run.id}`}>
                            <GitBranch size={14} />
                            Use as starting point
                          </StudioLink>
                          {!w.demo && (
                            <button
                              onClick={() =>
                                void exportRecord(run.id).catch((e) =>
                                  setError(e.message),
                                )
                              }
                            >
                              <Download size={14} />
                              Export record
                            </button>
                          )}
                        </div>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      {(cursor || nextCursor) && (
        <div className="pagination">
          <span>{items.length} experiments on this page</span>
          {cursor && (
            <Button label="First page" variant="secondary" size="sm" onClick={() => filter("cursor", "")} />
          )}
          {nextCursor && (
            <Button
              label="Next page"
              variant="secondary"
              size="sm"
              endContent={<ArrowRight size={15} />}
              onClick={() => {
                const next = new URLSearchParams(params);
                next.set("cursor", nextCursor);
                setParams(next);
              }}
            />
          )}
        </div>
      )}
    </section>
  );
}
