import { useId, useMemo, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { IconButton } from "@astryxdesign/core/IconButton";
import { TextArea } from "@astryxdesign/core/TextArea";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  Copy,
  Info,
  Pin,
  AlertTriangle,
  Save,
} from "lucide-react";
import { displayNumber, type Candidate, type Structure } from "./data";
import { candidateExplanation, candidateFailure } from "./candidateReview";
export function EvidencePanel({
  candidate,
  structure,
  pinned,
  onPin,
  onFocus,
  selectedResidue,
  note,
  onNote,
  onSaveNote,
  noteSaving,
  noteSaved,
  demo,
  readOnly = false,
}: {
  candidate: Candidate;
  structure?: Structure;
  pinned: boolean;
  onPin: () => void;
  onFocus: (residueId: string) => void;
  selectedResidue?: string;
  note: string;
  onNote: (text: string) => void;
  onSaveNote: () => void;
  noteSaving: boolean;
  noteSaved: boolean;
  demo: boolean;
  readOnly?: boolean;
}) {
  const inspectorId = useId();
  const groups = useMemo(
    () =>
      Object.values(
        (structure?.contacts ?? []).reduce<
          Record<string, NonNullable<typeof structure>["contacts"]>
        >((acc, c) => {
          (acc[c.residueId] ??= []).push(c);
          return acc;
        }, {}),
      ),
    [structure],
  );
  const [tab, setTab] = useState<"pose" | "properties" | "notes">("pose");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const assessed = candidate.checks !== "unavailable";
  const preparation = structure?.hydrogenPreparation;
  return (
    <aside
      className="evidence-panel evidence-inspector-v5"
      aria-label="Candidate evidence"
    >
      <div className="panel-heading">
        <h2>Evidence</h2>
        {readOnly && <span className="inspector-readonly">Read-only pose</span>}
      </div>
      <strong className="inspector-candidate-name">{candidate.name}</strong>
      <div
        className="tab-list inspector-tabs"
        role="tablist"
        aria-label="Evidence"
        onKeyDown={(event) => {
          const tabs = ["pose", "properties", "notes"] as const;
          const index = tabs.indexOf(tab);
          const next =
            event.key === "ArrowRight"
              ? tabs[(index + 1) % tabs.length]
              : event.key === "ArrowLeft"
                ? tabs[(index + tabs.length - 1) % tabs.length]
                : event.key === "Home"
                  ? tabs[0]
                  : event.key === "End"
                    ? tabs[2]
                    : undefined;
          if (!next) return;
          event.preventDefault();
          setTab(next);
          event.currentTarget
            .querySelector<HTMLButtonElement>(`[data-evidence-tab="${next}"]`)
            ?.focus();
        }}
      >
        <button
          role="tab"
          id={`${inspectorId}-pose`}
          data-evidence-tab="pose"
          aria-controls={`${inspectorId}-body`}
          tabIndex={tab === "pose" ? 0 : -1}
          aria-selected={tab === "pose"}
          onClick={() => setTab("pose")}
        >
          Pose
        </button>
        <button
          role="tab"
          id={`${inspectorId}-properties`}
          data-evidence-tab="properties"
          aria-controls={`${inspectorId}-body`}
          tabIndex={tab === "properties" ? 0 : -1}
          aria-selected={tab === "properties"}
          onClick={() => setTab("properties")}
        >
          Properties
        </button>
        <button
          role="tab"
          id={`${inspectorId}-notes`}
          data-evidence-tab="notes"
          aria-controls={`${inspectorId}-body`}
          tabIndex={tab === "notes" ? 0 : -1}
          aria-selected={tab === "notes"}
          onClick={() => setTab("notes")}
        >
          Notes
        </button>
      </div>
      <div
        className="evidence-body"
        key={candidate.id + tab}
        role="tabpanel"
        id={`${inspectorId}-body`}
        aria-labelledby={`${inspectorId}-${tab}`}
        tabIndex={0}
      >
        {tab === "pose" ? (
          <>
            {candidate.origin === "generated" && (
              <div
                className={`pose-outcome ${assessed && candidate.asp86Contact ? "detected" : ""}`}
              >
                {assessed && candidate.asp86Contact ? (
                  <Check size={16} />
                ) : (
                  <Info size={16} />
                )}
                <strong>
                  {!assessed
                    ? "Contact not assessed"
                    : candidate.asp86Contact === undefined
                      ? "Contact result unavailable"
                      : candidate.asp86Contact
                        ? "Asp86 contact detected"
                        : "No Asp86 H-bond detected"}
                </strong>
              </div>
            )}
            <p className="evidence-origin">
              {candidate.origin === "observed"
                ? `Observed crystal pose · ${candidate.receptorId}`
                : assessed
                  ? `${candidate.recorded ? "Recorded computed" : "Computed"} pose · not a measurement`
                  : candidateExplanation(candidate)}
            </p>
            {candidate.stereochemistryNote && (
              <div className="evidence-identity-warning" role="note" aria-label="Stereochemistry warning">
                <strong>Stereochemistry unspecified</strong>
                <p>{candidate.stereochemistryNote}</p>
              </div>
            )}
            {preparation?.warnings.some(
              (warning) => warning.code === "oh_orientation_not_sampled",
            ) && (
              <p className="evidence-preparation-warning">
                <Info size={13} />
                OH orientation not sampled. See calculation details.
              </p>
            )}
            <div className="evidence-section">
              <h3>
                Contact map{" "}
                <span>{structure?.contacts.length ?? candidate.contacts}</span>
              </h3>
              {groups.length ? (
                groups.map((cs) => {
                  const c = cs[0];
                  const distances = cs.map((x) => x.distance);
                  return (
                    <div className="contact-group" key={c.residueId}>
                      <button
                        className={`contact-row ${selectedResidue === c.residueId ? "focused" : ""}`}
                        aria-expanded={selectedResidue === c.residueId}
                        aria-controls={`contact-atoms-${c.residueId}`}
                        onClick={() => onFocus(c.residueId)}
                      >
                        <span>
                          <i />
                          {c.residueLabel.toUpperCase()}
                          <small>
                            {cs.length}{" "}
                            {cs.length === 1 ? "contact" : "contacts"}
                          </small>
                        </span>
                        <span className="contact-distance">
                          {Math.min(...distances).toFixed(2)}
                          {cs.length > 1
                            ? `–${Math.max(...distances).toFixed(2)}`
                            : ""}{" "}
                          Å <ChevronRight size={12} />
                        </span>
                      </button>
                      {selectedResidue === c.residueId && (
                        <ul
                          className="contact-atom-details"
                          id={`contact-atoms-${c.residueId}`}
                        >
                          {cs.map((contact) => {
                            const ligand = structure?.ligandAtoms.find(
                              (atom) => atom.id === contact.ligandAtom,
                            );
                            const protein = structure?.pocketAtoms?.find(
                              (atom) => atom.id === contact.proteinAtom,
                            );
                            const aspPart =
                              /^asp86$/i.test(contact.residueLabel) && protein
                                ? ["N", "CA", "C", "O"].includes(protein.name)
                                  ? "backbone"
                                  : "side chain"
                                : "";
                            return (
                              <li key={contact.id}>
                                <strong>
                                  Ligand {ligand?.name ?? contact.ligandAtom} ↔{" "}
                                  {contact.residueLabel.toUpperCase()}{" "}
                                  {protein?.name ?? contact.proteinAtom}
                                  {aspPart ? ` · ${aspPart}` : ""}
                                </strong>
                                <span>
                                  {contact.distance.toFixed(2)} Å donor–acceptor
                                  {typeof contact.angle === "number"
                                    ? ` · ${contact.angle.toFixed(1)}° D–H–A`
                                    : ""}
                                </span>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  );
                })
              ) : (
                <p className="muted">
                  {!assessed
                    ? "No pose available for contact inspection."
                    : structure
                      ? "No hydrogen-bond contacts detected in this pose."
                      : "Loading contact geometry…"}
                </p>
              )}
              <p className="fine-print">
                Hydrogen-bond donor–acceptor distances. Click a residue to focus
                its contacts.
              </p>
            </div>
            <div className="evidence-section">
              <h3>Geometry</h3>
              <dl className="evidence-dl">
                <div>
                  <dt>Pose checks</dt>
                  <dd
                    className={
                      candidate.checks === "pass" ? "text-teal" : "text-amber"
                    }
                  >
                    {candidate.checks === "pass" ? (
                      <>
                        <Check size={13} /> Pass
                      </>
                    ) : candidate.checks === "fail" ? (
                      "Needs review"
                    ) : (
                      "Not assessed"
                    )}
                  </dd>
                </div>
                {candidate.origin === "generated" && (
                  <div>
                    <dt>Design review</dt>
                    <dd
                      className={
                        candidate.reviewReady ? "text-teal" : "text-amber"
                      }
                    >
                      {candidate.reviewReady
                        ? "Ready to inspect"
                        : assessed
                          ? "Outside design brief"
                          : "Not assessed"}
                    </dd>
                  </div>
                )}
                {candidate.ringDriftA !== undefined && (
                  <div>
                    <dt title="Purine-ring RMSD relative to the parent in the protein coordinate frame">
                      Ring shift
                    </dt>
                    <dd>{displayNumber(candidate.ringDriftA)} Å</dd>
                  </div>
                )}
                <div>
                  <dt>Receptor</dt>
                  <dd>
                    {candidate.receptorId}{" "}
                    <span className="muted">
                      {candidate.origin === "observed"
                        ? "· matched"
                        : "· fixed"}
                    </span>
                  </dd>
                </div>
                {candidate.score !== undefined && (
                  <div>
                    <dt>
                      Vina score <small>kcal/mol</small>
                    </dt>
                    <dd>{displayNumber(candidate.score)}</dd>
                  </div>
                )}
              </dl>
              {candidate.failures.length > 0 && (
                <div className="failure-note">
                  <AlertTriangle size={14} />
                  <span>
                    {candidate.failures
                      .map((failure) => candidateFailure(candidate, failure))
                      .join(" ")}
                  </span>
                </div>
              )}
            </div>
            {candidate.origin === "generated" &&
              (Boolean(candidate.embeddingErrors?.length) ||
                Boolean(candidate.poseErrors?.length) ||
                candidate.stereochemistryNote ||
                candidate.selectionPolicy ||
                preparation ||
                Boolean(candidate.poseCount)) && (
                <details className="pose-calculation-details">
                  <summary>
                    Calculation details
                    {candidate.poseCount
                      ? ` · ${candidate.poseCount} ${candidate.poseCount === 1 ? "pose" : "poses"}`
                      : ""}
                  </summary>
                  {candidate.selectionPolicy && (
                    <p>
                      <strong>Protocol selection:</strong>{" "}
                      {candidate.selectionPolicy}. This rule selects the
                      protocol pose; the pose menu also exposes alternatives.
                    </p>
                  )}
                  {preparation && (
                    <div className="hydrogen-preparation">
                      <h3>Hydrogen preparation</h3>
                      <p>{preparation.note}</p>
                      {preparation.warnings.map((warning) => (
                        <p key={warning.code}>{warning.message}</p>
                      ))}
                      {preparation.warnings.length > 0 &&
                        !preparation.orientation_sensitivity_assessed && (
                          <p>
                            This flags an untested preparation choice; it is not
                            a measured sensitivity result.
                          </p>
                        )}
                    </div>
                  )}
                  {Boolean(candidate.embeddingErrors?.length) && (
                    <details className="calculation-failures">
                      <summary>
                        {candidate.embeddingErrors!.length} starting
                        conformation attempts failed
                      </summary>
                      <p>
                        These attempts could not create a starting 3D
                        arrangement. Any successful attempts were kept.
                      </p>
                      <ul>
                        {candidate.embeddingErrors!.map((error, index) => (
                          <li key={`${error.attempt}-${index}`}>
                            <strong>
                              Attempt {error.attempt} · seed {error.seed}
                            </strong>
                            <span>{error.error || error.status}</span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {Boolean(candidate.poseErrors?.length) && (
                    <details className="calculation-failures">
                      <summary>
                        {candidate.poseErrors!.length} pose evaluations failed
                      </summary>
                      <p>
                        Successful pose evaluations were kept with their exact
                        evidence.
                      </p>
                      <ul>
                        {candidate.poseErrors!.map((error, index) => (
                          <li key={`${error.id}-${index}`}>
                            <strong>{error.id || `Pose ${index + 1}`}</strong>
                            <span>{error.message || error.kind}</span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {Boolean(candidate.poseCount) && (
                    <small>
                      {candidate.poseCount} completed{" "}
                      {candidate.poseCount === 1 ? "pose" : "poses"} ·
                      alternatives retain their prepared-state identity
                    </small>
                  )}
                </details>
              )}
            <details className="evidence-section interpretation">
              <summary>How to read this evidence</summary>
              <p>
                {candidate.origin === "observed"
                  ? "Contacts describe the observed binding geometry. They do not measure potency."
                  : "A lower score is not proof of stronger binding. Geometry and receptor context come first."}
              </p>
            </details>
            {candidate.sourceUrl && (
              <a
                className="source-link"
                href={candidate.sourceUrl}
                target="_blank"
                rel="noreferrer"
              >
                View structure at RCSB <ArrowUpRight size={13} />
              </a>
            )}
          </>
        ) : tab === "properties" ? (
          <>
            {candidate.depictionUrl && (
              <img
                className="molecule-2d"
                src={candidate.depictionUrl}
                alt={`${candidate.name} molecular structure`}
              />
            )}
            <div className="evidence-section">
              <h3>Calculated properties</h3>
              {candidate.preparedMoleculeId && (
                <p className="prepared-state-note">
                  Prepared state{" "}
                  <code>{candidate.preparedMoleculeId.slice(0, 12)}</code>. The
                  structure below belongs to the displayed pose; other states
                  may have different stereochemistry.
                </p>
              )}
              <dl className="evidence-dl">
                <div>
                  <dt>Molecular weight</dt>
                  <dd>
                    {displayNumber(candidate.mw, 1)}{" "}
                    <span className="muted">Da</span>
                  </dd>
                </div>
                <div>
                  <dt>cLogP</dt>
                  <dd>{displayNumber(candidate.clogp)}</dd>
                </div>
                <div>
                  <dt>Rotatable bonds</dt>
                  <dd>{displayNumber(candidate.rotors, 0)}</dd>
                </div>
                <div>
                  <dt>Formal charge</dt>
                  <dd>{displayNumber(candidate.charge, 0)}</dd>
                </div>
              </dl>
              <p className="fine-print">
                Calculated with RDKit. cLogP estimates preference for oily
                versus watery surroundings.
              </p>
            </div>
            <div className="smiles-block">
              <div>
                <h3>
                  {candidate.status === "invalid"
                    ? "Submitted input"
                    : candidate.proposalSmiles &&
                        candidate.proposalSmiles !== candidate.smiles
                      ? "Prepared SMILES"
                      : "SMILES"}
                </h3>
                <IconButton
                  label="Copy SMILES"
                  variant="ghost"
                  size="sm"
                  icon={copied ? <Check size={14} /> : <Copy size={14} />}
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(candidate.smiles);
                      setCopied(true);
                      setCopyError(false);
                      setTimeout(() => setCopied(false), 1500);
                    } catch {
                      setCopyError(true);
                    }
                  }}
                />
              </div>
              <code>{candidate.smiles || "No valid molecular structure"}</code>
              {copyError && (
                <p className="fine-print">
                  Clipboard unavailable. Select the structure text to copy it.
                </p>
              )}
              {candidate.proposalSmiles &&
                candidate.proposalSmiles !== candidate.smiles && (
                  <>
                    <h3>Original proposal</h3>
                    <code>{candidate.proposalSmiles}</code>
                  </>
                )}
            </div>
          </>
        ) : (
          <>
            <div className="evidence-section">
              <h3>Your review</h3>
              <p className="muted">
                Keep the reason behind your next decision.
              </p>
              <div className="inspector-note-field">
                <TextArea
                  label={`Notes for ${candidate.name}`}
                  isLabelHidden
                  value={note}
                  onChange={onNote}
                  placeholder="What changed? What should we test next?"
                  rows={8}
                  isReadOnly={readOnly}
                />
              </div>
              <div className="note-save-row">
                <Button
                  label={
                    noteSaving ? "Saving…" : noteSaved ? "Saved" : "Save note"
                  }
                  icon={<Save size={14} />}
                  size="sm"
                  isLoading={noteSaving}
                  isDisabled={readOnly || noteSaved}
                  onClick={onSaveNote}
                />
                <span role="status">
                  {noteSaved ? <Check size={14} /> : null}
                </span>
              </div>
              <p className="fine-print">
                {demo || candidate.origin === "observed"
                  ? "Reference notes stay in this browser."
                  : "Saved with this experiment in your local database."}
              </p>
            </div>
          </>
        )}
      </div>
      <div className="inspector-footer">
        <Button
          className="inspector-pin-v5"
          label={pinned ? "Pinned to comparison" : "Pin to comparison"}
          icon={<Pin size={14} />}
          variant="secondary"
          size="sm"
          aria-pressed={pinned}
          onClick={onPin}
          isDisabled={readOnly}
        />
      </div>
    </aside>
  );
}
