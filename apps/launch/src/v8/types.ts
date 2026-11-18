import type source from "./source.json";

type MolecularRecord = (typeof source.native)[number]["scene"]["record"];

export type Point = [number, number, number];
export type View = {
  eye: Point;
  target: Point;
  fov: number;
  offset?: [number, number];
};
export type CameraKeyframe = { frame: number; view: View };
export type CropKeyframe = {
  frame: number;
  x: number;
  y: number;
  scale: number;
  insetX: number;
  insetY: number;
};
export type FilmOverlay = {
  fromFrame: number;
  durationFrames: number;
  text: string;
  secondary?: string;
  position: "top" | "bottom";
};
export type SourceSegment = {
  id: string;
  fromFrame: number;
  durationFrames: number;
  kind: "video" | "held-source-frame";
  src: string;
  sourceStartFrame?: number;
  crop?: CropKeyframe[];
  detailInsert?: {
    fromFrame: number;
    toFrame: number;
    rect: { x: number; y: number; width: number; height: number };
    scale: number;
    center: [number, number];
    matte: string;
  };
  recordedPointer?: {
    fromSourceSeconds: number;
    toSourceSeconds: number;
    eventToVideoOffsetSeconds: number;
    events: {
      type: string;
      elapsedSeconds: number;
      x: number;
      y: number;
      button: number;
    }[];
  };
};
export type MolecularScene = {
  record: MolecularRecord;
  origin: Point;
  contactId?: string;
};
export type NativeSegment = {
  id: string;
  fromFrame: number;
  durationFrames: number;
  scene: MolecularScene;
  camera: CameraKeyframe[];
  contactOpacity?: number;
  title?: string;
  measurement?: { distance: number; atomLabel: string };
};

/** Actual source bindings, populated only after the fresh live take passes review. */
export type VerifiedSourceV8 = {
  status: "verified-live-capture";
  fps: 30;
  width: 1920;
  height: 1080;
  durationFrames: number;
  experimentId: string;
  submittedExperimentId: string;
  exportedExperimentId: string;
  candidateId: string;
  poseId: string;
  observedWaitSeconds: number;
  captureManifestSha256: string;
  sourceRasterVerified: true;
  segments: SourceSegment[];
  native: NativeSegment[];
  overlays: FilmOverlay[];
  closingFromFrame: number;
};
