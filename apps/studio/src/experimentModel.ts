import type { ExperimentConfig } from "./experimentConfig";
export type ExperimentRun = {
  id: string;
  name: string;
  createdAt: string;
  status:
    | "queued"
    | "running"
    | "completed"
    | "completed_with_errors"
    | "cancelled"
    | "failed";
  stage: string;
  candidateCount: number;
  config: ExperimentConfig;
  parentId?: string;
  elapsedSeconds?: number;
  message?: string;
  completedCandidates?: number;
  totalCandidates?: number;
  objectiveHits?: number;
  latestSequence?: number;
  errorCount?: number;
  poseFailureCount?: number;
  embeddingFailureCount?: number;
  recorded?: boolean;
  spec?: unknown;
};
export const isActive = (run: ExperimentRun) =>
  run.status === "running" || run.status === "queued";
export const isFinished = (run: ExperimentRun) =>
  run.status === "completed" || run.status === "completed_with_errors";
