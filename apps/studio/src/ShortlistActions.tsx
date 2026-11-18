import { ArrowRight, GitBranch, Layers, Pin } from "lucide-react";
import { Button } from "@astryxdesign/core/Button";
import { useStudio, useStudioNavigate, StudioLink } from "./StudioContext";
import type { Candidate } from "./data";
import type { ExperimentConfig, OriginCandidate } from "./experimentConfig";
import { DEFAULT_STUDY_SEEDS, saveStudyDraft } from "./studyModel";
import "./study.css";

export function ShortlistActions({
  experimentId,
  candidates,
}: {
  experimentId: string;
  candidates: Candidate[];
}) {
  const w = useStudio(),
    navigate = useStudioNavigate();
  const run = w.runs.find((r) => r.id === experimentId);
  const selected = candidates.filter(
    (c) =>
      w.pins.includes(c.id) &&
      c.smiles &&
      c.status !== "invalid" &&
      c.status !== "duplicate",
  );
  if (!run || !selected.length) return null;
  const origins: OriginCandidate[] = selected.map((c) => ({
    name: c.name,
    smiles: c.smiles,
    origin: {
      experiment_id: run.id,
      candidate_id: c.id,
      ...(c.structureId ? { pose_id: c.structureId } : {}),
    },
  }));
  const config: ExperimentConfig = {
    ...run.config,
    name: `${run.name} · shortlist`.slice(0, 160),
    source: "supplied",
    suppliedText: selected.map((c) => `${c.smiles} ${c.name}`).join("\n"),
    parentId: run.id,
    originCandidates: origins,
  };
  const newRound = () => {
    w.saveDraft({
      config,
      step: 0,
      parentName: run.name,
      savedAt: new Date().toISOString(),
    });
    navigate("/experiments/new");
  };
  const newStudy = () => {
    saveStudyDraft(w.demo, {
      config: {
        ...config,
        name: `${run.name} · repeat-seed shortlist`.slice(0, 160),
      },
      seeds: DEFAULT_STUDY_SEEDS.map((s) => ({ ...s })),
      step: 0,
      sourceName: run.name,
    });
    navigate("/studies/new");
  };
  return (
    <div
      className="shortlist-actions compact-shortlist-v5"
      aria-label="Pinned candidate actions"
    >
      <span>
        <Pin size={13} /> {selected.length} pinned{" "}
        {selected.length === 1 ? "candidate" : "candidates"}
      </span>
      <StudioLink className="text-link" to={`/experiments/${run.id}/compare`}>
        Compare <ArrowRight size={14} />
      </StudioLink>
      <Button
        label="New round"
        aria-label="Use shortlist in a new round"
        icon={<GitBranch size={15} />}
        size="sm"
        variant="ghost"
        onClick={newRound}
      />
      <Button
        label="Test across seeds"
        aria-label="Evaluate shortlist across seeds"
        icon={<Layers size={15} />}
        size="sm"
        variant="secondary"
        onClick={newStudy}
      />
    </div>
  );
}
