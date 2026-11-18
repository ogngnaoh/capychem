import type { ReactNode } from "react";
import {
  ArrowRight,
  Check,
  LoaderCircle,
  TriangleAlert,
  Square,
  RefreshCw,
} from "lucide-react";
import { StudioLink } from "./StudioContext";
import type { ExperimentRun } from "./experimentModel";
import { API_BASE } from "./api";
import { download } from "./data";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="product-page-header">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
export const statusNames: Record<ExperimentRun["status"], string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  completed_with_errors: "Partial results",
  failed: "Failed",
  cancelled: "Cancelled",
};
export function StatusLabel({ status }: { status: ExperimentRun["status"] }) {
  const active = status === "running" || status === "queued";
  return (
    <span className={`status-label status-${status}`}>
      {active ? (
        <LoaderCircle size={14} className="spin" aria-hidden="true" />
      ) : status === "completed" ? (
        <Check size={14} aria-hidden="true" />
      ) : status === "cancelled" ? (
        <Square size={12} aria-hidden="true" />
      ) : (
        <TriangleAlert size={14} aria-hidden="true" />
      )}{" "}
      {statusNames[status] ?? status}
    </span>
  );
}
export function EmptyState({
  title,
  body,
  action,
  icon,
}: {
  title: string;
  body: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="product-empty">
      {icon && <span className="product-empty-icon" aria-hidden="true">{icon}</span>}
      <h2>{title}</h2>
      <p>{body}</p>
      {action && <div className="product-empty-actions">{action}</div>}
    </div>
  );
}
export function InlineError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="product-error" role="alert">
      <TriangleAlert size={18} aria-hidden="true" />
      <div className="product-error-message">{message}</div>
      {onRetry && (
        <button type="button" className="secondary-button" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden="true" />
          Try again
        </button>
      )}
    </div>
  );
}
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="product-loading" role="status" aria-atomic="true">
      <LoaderCircle size={20} className="spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
export function NotFoundPage({ experiment = false }: { experiment?: boolean }) {
  return (
    <section className="product-page">
      <PageHeader
        title={experiment ? "Experiment not found" : "Page not found"}
      />
      <EmptyState
        title={
          experiment
            ? "This experiment is unavailable"
            : "There is no page at this address"
        }
        body={
          experiment
            ? "Choose a saved experiment from the collection to continue."
            : "This address does not match a page in CapyChem."
        }
        action={
          <div className="action-row">
            <StudioLink className="primary-link" to="/">
              Go to overview <ArrowRight size={16} />
            </StudioLink>
            <StudioLink className="secondary-button" to="/experiments">
              View experiments
            </StudioLink>
          </div>
        }
      />
    </section>
  );
}
export function readableDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(date);
}
export async function exportRecord(id: string) {
  const response = await fetch(
    `${API_BASE}/experiments/${encodeURIComponent(id)}/export`,
  );
  if (!response.ok)
    throw new Error(
      "The experiment record could not be exported. Check the local API and retry.",
    );
  download(`capychem-${id}.json`, await response.text());
}
