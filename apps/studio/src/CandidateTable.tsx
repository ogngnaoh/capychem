import {
  Search,
  Pin,
  ArrowUpDown,
  ArrowUpRight,
  FlaskConical,
  Plus,
  List,
  Table2,
} from "lucide-react";
import { useId, useMemo, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { IconButton } from "@astryxdesign/core/IconButton";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Selector } from "@astryxdesign/core/Selector";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@astryxdesign/core/SegmentedControl";
import { displayNumber, type Candidate } from "./data";
import {
  candidateExplanation,
  candidateStatus,
  matchesOutcome,
  objectiveStatus,
  type OutcomeFilter,
} from "./candidateReview";
export function CandidateTable({
  candidates,
  selectedId,
  pinned,
  onSelect,
  onPin,
  mode,
  onMode,
  hasRun,
  demo,
  runName,
  onNew,
  readOnly = false,
  sourceLabel,
  presentation = "table",
  onPresentationChange,
}: {
  candidates: Candidate[];
  selectedId: string;
  pinned: string[];
  onSelect: (id: string) => void;
  onPin: (id: string) => void;
  mode: "references" | "generated" | "pinned";
  onMode: (mode: "references" | "generated" | "pinned") => void;
  hasRun: boolean;
  demo: boolean;
  runName?: string;
  onNew: () => void;
  readOnly?: boolean;
  sourceLabel?: string;
  presentation?: "list" | "table";
  onPresentationChange?: (value: "list" | "table") => void;
}) {
  const collectionId = useId();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"name" | "clogp" | "checks">("name");
  const [direction, setDirection] = useState(1);
  const [outcome, setOutcome] = useState<OutcomeFilter>("all");
  const [controlsOpen, setControlsOpen] = useState(false);
  const chooseSort = (key: typeof sort) => {
    if (sort === key) setDirection((v) => -v);
    else {
      setSort(key);
      setDirection(1);
    }
  };
  const generated = candidates.filter((c) => c.origin === "generated");
  const outcomeOptions = (
    [
      ["all", "All inputs"],
      ["ready", "Ready to inspect"],
      ["objective", "Asp86 + ready"],
      ["review", "Outside brief"],
      ["unevaluated", "Not evaluated"],
    ] as const
  ).map(([value, label]) => ({
    value,
    label,
    count: generated.filter(
      (c) =>
        matchesOutcome(c, value) &&
        (mode !== "pinned" || pinned.includes(c.id)),
    ).length,
  }));
  const collection = hasRun ? "generated" : "references";
  const collections = [collection, "pinned"] as const;
  const rows = useMemo(
    () =>
      candidates
        .filter(
          (c) =>
            (mode === "references"
              ? c.origin === "observed"
              : mode === "generated"
                ? c.origin === "generated"
                : pinned.includes(c.id)) &&
            (!hasRun || matchesOutcome(c, outcome)) &&
            `${c.name} ${c.description} ${c.smiles}`
              .toLowerCase()
              .includes(query.toLowerCase()),
        )
        .sort(
          (a, b) =>
            direction *
            (sort === "clogp"
              ? (Number.isFinite(a.clogp) ? a.clogp : Infinity) -
                (Number.isFinite(b.clogp) ? b.clogp : Infinity)
              : sort === "checks"
                ? a.checks.localeCompare(b.checks)
                : a.name.localeCompare(b.name, undefined, { numeric: true })),
        ),
    [candidates, mode, pinned, query, sort, direction, hasRun, outcome],
  );
  return (
    <section
      className={`candidate-panel candidate-browser-v5 candidate-${presentation}`}
      aria-label="Candidates"
    >
      <div className="candidate-browser-heading">
        <h2>{hasRun ? "Candidates" : "Compounds"}</h2>
        {onPresentationChange && (
          <SegmentedControl
            label="Candidate presentation"
            value={presentation}
            onChange={(value) =>
              onPresentationChange(value as "list" | "table")
            }
            size="sm"
          >
            <SegmentedControlItem
              value="list"
              label="Candidate list"
              isLabelHidden
              icon={<List size={15} />}
            />
            <SegmentedControlItem
              value="table"
              label="Metrics table"
              isLabelHidden
              icon={<Table2 size={15} />}
            />
          </SegmentedControl>
        )}
      </div>
      <div className="table-toolbar">
        <div
          className="tab-list"
          role="tablist"
          aria-label="Candidate collections"
          onKeyDown={(event) => {
            const index = collections.indexOf(
              mode as (typeof collections)[number],
            );
            const next =
              event.key === "ArrowRight" || event.key === "ArrowLeft"
                ? collections[(index + 1) % collections.length]
                : event.key === "Home"
                  ? collection
                  : event.key === "End"
                    ? "pinned"
                    : undefined;
            if (!next) return;
            event.preventDefault();
            onMode(next);
            event.currentTarget
              .querySelector<HTMLButtonElement>(`[data-collection="${next}"]`)
              ?.focus();
          }}
        >
          {!hasRun && (
            <button
              role="tab"
              id={`${collectionId}-references`}
              data-collection="references"
              aria-controls={`${collectionId}-results`}
              tabIndex={mode === "references" ? 0 : -1}
              aria-selected={mode === "references"}
              onClick={() => onMode("references")}
            >
              References{" "}
              <span>
                {candidates.filter((c) => c.origin === "observed").length}
              </span>
            </button>
          )}
          {hasRun && (
            <button
              role="tab"
              id={`${collectionId}-generated`}
              data-collection="generated"
              aria-controls={`${collectionId}-results`}
              tabIndex={mode === "generated" ? 0 : -1}
              aria-selected={mode === "generated"}
              onClick={() => onMode("generated")}
            >
              Candidates <span>{generated.length}</span>
            </button>
          )}
          <button
            role="tab"
            id={`${collectionId}-pinned`}
            data-collection="pinned"
            aria-controls={`${collectionId}-results`}
            tabIndex={mode === "pinned" ? 0 : -1}
            aria-selected={mode === "pinned"}
            onClick={() => onMode("pinned")}
          >
            Pinned <span>{pinsVisible(candidates, pinned)}</span>
          </button>
        </div>
        <div className="table-search candidate-search-v5">
          <TextInput
            label="Filter compounds"
            aria-label="Filter compounds"
            isLabelHidden
            type="search"
            size="sm"
            startIcon={<Search size={15} />}
            hasClear
            placeholder="Find a compound…"
            value={query}
            onChange={setQuery}
          />
        </div>
      </div>
      {mode === "generated" && generated.length > 0 && (
        <details className="batch-outcome candidate-batch-v5">
          <summary>
            {generated.filter((c) => c.reviewReady).length} ready to inspect{" "}
            <span>of {generated.length} inputs</span>
          </summary>
          <span>
            {demo ? "Recorded batch" : runName || "Experiment results"} ·{" "}
            {generated.filter((c) => c.reviewReady).length} ready to inspect
          </span>
          <strong>
            {generated.some((c) => c.reviewReady && c.asp86Contact)
              ? "Review-ready Asp86 contact detected"
              : generated.some((c) => c.asp86Contact)
                ? "Asp86 contact only outside design brief"
                : generated.some((c) => c.checks !== "unavailable")
                  ? "No predicted Asp86 contact"
                  : "Contact hypothesis not assessed"}
          </strong>
          <span className="batch-limits">
            {generated.filter((c) => c.status === "outside_constraints").length}{" "}
            outside profile ·{" "}
            {generated.filter((c) => c.status === "deferred_budget").length}{" "}
            deferred
            {generated.some((c) => c.status === "duplicate") && (
              <>
                {" "}
                · {
                  generated.filter((c) => c.status === "duplicate").length
                }{" "}
                duplicate
              </>
            )}
            {generated.some((c) => c.status === "invalid") && (
              <>
                {" "}
                · {generated.filter((c) => c.status === "invalid").length}{" "}
                invalid
              </>
            )}
          </span>
        </details>
      )}
      {presentation === "list" && (
        <details
          className="candidate-list-controls"
          open={controlsOpen}
          onToggle={(event) => setControlsOpen(event.currentTarget.open)}
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            setControlsOpen(false);
            event.currentTarget.querySelector("summary")?.focus();
          }}
        >
          <summary>
            <ArrowUpDown size={13} aria-hidden="true" />
            <span>Filter & sort</span>
            {(outcome !== "all" || sort !== "name" || direction !== 1) && (
              <span className="candidate-controls-active">Active</span>
            )}
          </summary>
          <div className="candidate-control-fields">
          {hasRun && generated.length > 0 && (
            <Selector
              label="Filter candidate outcomes"
              isLabelHidden
              size="sm"
              value={outcome}
              onChange={(value) => setOutcome(value as OutcomeFilter)}
              options={[
                {
                  type: "section",
                  title: "Candidate outcomes",
                  options: outcomeOptions.map((option) => ({
                    value: option.value,
                    label: `${option.label} · ${option.count}`,
                  })),
                },
              ]}
            />
          )}
          <Selector
            label="Sort candidates"
            isLabelHidden
            size="sm"
            value={`${sort}:${direction}`}
            onChange={(value) => {
              const [key, order] = value.split(":");
              setSort(key as typeof sort);
              setDirection(Number(order));
            }}
            options={[
              {
                type: "section",
                title: "Sort candidates",
                options: [
                  { value: "name:1", label: "Name · A–Z" },
                  { value: "name:-1", label: "Name · Z–A" },
                  { value: "clogp:1", label: "cLogP · low to high" },
                  { value: "clogp:-1", label: "cLogP · high to low" },
                  { value: "checks:1", label: "Pose checks · A–Z" },
                  { value: "checks:-1", label: "Pose checks · Z–A" },
                ],
              },
            ]}
          />
          </div>
        </details>
      )}
      {presentation === "table" && hasRun && generated.length > 0 && (
        <div
          className="candidate-outcome-filters-v5"
          role="group"
          aria-label="Filter candidate outcomes"
        >
          {outcomeOptions.map(({ value, label, count }) => (
            <Button
              key={value}
              label={`${label} ${count}`}
              size="sm"
              variant={outcome === value ? "secondary" : "ghost"}
              aria-pressed={outcome === value}
              onClick={() => setOutcome(value)}
            />
          ))}
        </div>
      )}
      <div
        className={
          presentation === "list" ? "candidate-list-scroll" : "table-scroll"
        }
        role="tabpanel"
        id={`${collectionId}-results`}
        aria-labelledby={`${collectionId}-${mode}`}
        tabIndex={0}
      >
        {presentation === "list" ? (
          <ul
            className="candidate-object-list"
            aria-label="Candidate compounds"
          >
            {rows.map((c) => (
              <li key={c.id} className={selectedId === c.id ? "selected" : ""}>
                <button
                  className="candidate-object-select"
                  aria-label={c.name}
                  aria-pressed={selectedId === c.id}
                  onClick={() => onSelect(c.id)}
                  title={candidateExplanation(c)}
                >
                  {c.depictionUrl ? (
                    <img
                      src={c.depictionUrl}
                      alt=""
                      loading="lazy"
                      className="candidate-object-depiction"
                    />
                  ) : (
                    <span
                      className="candidate-object-no-depiction"
                      aria-hidden="true"
                    >
                      —
                    </span>
                  )}
                  <span className="candidate-object-copy">
                    <strong>{c.name}</strong>
                    <span
                      className={`candidate-object-status ${c.reviewReady ? "ready" : ""}`}
                    >
                      {candidateStatus(c)}
                    </span>
                    <span className="candidate-object-contact">
                      {c.origin === "observed"
                        ? `${c.receptorId} · crystal pose`
                        : `Asp86: ${objectiveStatus(c).toLowerCase()}`}
                    </span>
                  </span>
                </button>
                <IconButton
                  className={`candidate-object-pin ${pinned.includes(c.id) ? "pinned" : ""}`}
                  label={`${pinned.includes(c.id) ? "Unpin" : "Pin"} ${c.name}`}
                  icon={<Pin size={14} />}
                  variant="ghost"
                  size="sm"
                  aria-pressed={pinned.includes(c.id)}
                  isDisabled={readOnly}
                  onClick={() => onPin(c.id)}
                />
              </li>
            ))}
          </ul>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="pin-cell">
                  <Pin size={13} />
                  <span className="sr-only">Pin</span>
                </th>
                <th
                  aria-sort={
                    sort === "name"
                      ? direction === 1
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button onClick={() => chooseSort("name")}>
                    Compound <ArrowUpDown size={12} />
                  </button>
                </th>
                <th>Source</th>
                <th
                  aria-sort={
                    sort === "checks"
                      ? direction === 1
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button onClick={() => chooseSort("checks")}>
                    Pose checks <ArrowUpDown size={12} />
                  </button>
                </th>
                <th>{hasRun ? "Asp86 contact" : "Pocket evidence"}</th>
                {hasRun && <th>Design review</th>}
                <th
                  aria-sort={
                    sort === "clogp"
                      ? direction === 1
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button onClick={() => chooseSort("clogp")}>
                    cLogP <ArrowUpDown size={12} />
                  </button>
                </th>
                <th>
                  <span className="sr-only">Open compound</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr
                  key={c.id}
                  className={selectedId === c.id ? "selected" : ""}
                  onClick={() => onSelect(c.id)}
                >
                  <td>
                    <IconButton
                      className={`candidate-table-pin ${pinned.includes(c.id) ? "pinned" : ""}`}
                      label={`${pinned.includes(c.id) ? "Unpin" : "Pin"} ${c.name}`}
                      icon={<Pin size={14} />}
                      size="sm"
                      variant="ghost"
                      aria-pressed={pinned.includes(c.id)}
                      isDisabled={readOnly}
                      onClick={(e) => {
                        e.stopPropagation();
                        onPin(c.id);
                      }}
                    />
                  </td>
                  <td>
                    <button
                      className="compound-name"
                      onClick={() => onSelect(c.id)}
                    >
                      {c.name}
                    </button>
                    <span
                      className="compound-desc"
                      title={
                        c.origin === "generated"
                          ? candidateExplanation(c)
                          : c.description
                      }
                    >
                      {c.origin === "generated" && !c.structureId
                        ? candidateStatus(c)
                        : c.description}
                    </span>
                  </td>
                  <td>
                    <span className={`source-label ${c.origin}`}>
                      {c.origin === "observed"
                        ? "Observed reference"
                        : c.recorded
                          ? "Recorded prediction"
                          : (sourceLabel ?? "Local calculation")}
                    </span>
                  </td>
                  <td>
                    <span className={`check-status ${c.checks}`}>
                      <i />
                      {c.checks === "pass"
                        ? "Pass"
                        : c.checks === "fail"
                          ? "Needs review"
                          : c.status === "deferred_budget"
                            ? "Deferred"
                            : c.status === "outside_constraints"
                              ? "Excluded"
                              : c.status === "invalid"
                                ? "Invalid"
                                : c.status === "queued"
                                  ? "Queued"
                                  : c.status === "duplicate"
                                    ? "Duplicate"
                                    : "No pose"}
                    </span>
                  </td>
                  <td>
                    {hasRun ? (
                      <span
                        className={
                          c.reviewReady && c.asp86Contact
                            ? "text-teal"
                            : "muted"
                        }
                      >
                        {objectiveStatus(c)}
                      </span>
                    ) : c.checks === "unavailable" ? (
                      <span className="muted">Not assessed</span>
                    ) : (
                      <span>
                        {c.contacts} detected{" "}
                        {c.contacts === 1 ? "contact" : "contacts"}
                      </span>
                    )}
                  </td>
                  {hasRun && (
                    <td>
                      <span
                        className={c.reviewReady ? "text-teal" : "muted"}
                        title={candidateExplanation(c)}
                      >
                        {c.reviewReady
                          ? "Ready"
                          : c.structureId
                            ? "Outside brief"
                            : "Not evaluated"}
                      </span>
                    </td>
                  )}
                  <td className="numeric">{displayNumber(c.clogp)}</td>
                  <td>
                    <ArrowUpRight size={15} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {rows.length === 0 && (
          <div className="table-empty">
            <FlaskConical size={22} />
            <strong>
              {query || outcome !== "all"
                ? "No compounds match"
                : mode === "pinned"
                  ? "Keep the candidates worth a closer look"
                  : hasRun
                    ? "No candidates in this collection"
                    : "Explore your first design batch"}
            </strong>
            <p>
              {query || outcome !== "all"
                ? "Try another outcome filter or clear your search. All inputs remain in this experiment."
                : mode === "pinned"
                  ? "Pin compounds to compare their evidence."
                  : demo
                    ? "Open the recorded experiment from History to explore its results."
                    : "Evaluate a known series or let LibInvent propose side groups."}
            </p>
            {(query || outcome !== "all") && (
              <Button
                label="Show all inputs"
                size="sm"
                onClick={() => {
                  setQuery("");
                  setOutcome("all");
                }}
              />
            )}
            {!query && mode === "generated" && !hasRun && (
              <Button
                label="New experiment"
                size="sm"
                icon={<Plus size={14} />}
                onClick={onNew}
              />
            )}
          </div>
        )}
      </div>
      <div className="table-footer">
        <span>
          {rows.length}{" "}
          {mode === "references"
            ? "reference compounds"
            : mode === "pinned"
              ? "pinned compounds"
              : "candidates"}
        </span>
        <span>
          {mode === "references"
            ? "Crystal poses · matching receptors"
            : demo
              ? "Recorded computational results"
              : "Exact inputs · reproducible evidence"}
        </span>
      </div>
    </section>
  );
}
function pinsVisible(candidates: Candidate[], pinned: string[]) {
  return candidates.filter((c) => pinned.includes(c.id)).length;
}
