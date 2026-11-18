import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  Interactive,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { FilmFrame } from "../components/Frame";
import { MolecularWorld, contactGeometry, project } from "./MolecularWorld";
import type {
  CameraKeyframe,
  CropKeyframe,
  NativeSegment,
  Point,
  SourceSegment,
  VerifiedSourceV8,
  View,
} from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.65, 0, 0.18, 1);
const ramp = (frame: number, start: number, end: number) =>
  interpolate(frame, [start, end], [0, 1], { ...clamp, easing: ease });
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const point = (a: Point, b: Point, t: number) =>
  a.map((v, i) => lerp(v, b[i], t)) as Point;
function pair<T extends { frame: number }>(
  keys: T[],
  frame: number,
): [T, T, number] {
  if (!keys.length)
    throw new Error("A camera/crop needs actual reviewed keyframes.");
  const index = keys.findIndex((k) => k.frame > frame);
  if (index === 0) return [keys[0], keys[0], 0];
  if (index < 0) return [keys[keys.length - 1], keys[keys.length - 1], 0];
  const a = keys[index - 1],
    b = keys[index];
  return [a, b, ramp(frame, a.frame, b.frame)];
}
function cameraAt(keys: CameraKeyframe[], frame: number): View {
  const [a, b, t] = pair(keys, frame);
  return {
    eye: point(a.view.eye, b.view.eye, t),
    target: point(a.view.target, b.view.target, t),
    fov: lerp(a.view.fov, b.view.fov, t),
    offset: [
      lerp(a.view.offset?.[0] || 0, b.view.offset?.[0] || 0, t),
      lerp(a.view.offset?.[1] || 0, b.view.offset?.[1] || 0, t),
    ],
  };
}
const whole: CropKeyframe = {
  frame: 0,
  x: 0,
  y: 0,
  scale: 1,
  insetX: 0,
  insetY: 0,
};
function cropAt(keys: CropKeyframe[] | undefined, frame: number) {
  const [a, b, t] = pair(keys?.length ? keys : [whole], frame);
  const scale = lerp(a.scale, b.scale, t);
  return {
    x: Math.max((1 - scale) * 1920, Math.min(0, lerp(a.x, b.x, t))),
    y: Math.max((1 - scale) * 1080, Math.min(0, lerp(a.y, b.y, t))),
    scale,
    insetX: lerp(a.insetX, b.insetX, t),
    insetY: lerp(a.insetY, b.insetY, t),
  };
}

function RecordedClip({
  segment,
  frame,
  offset,
}: {
  segment: SourceSegment;
  frame: number;
  offset: number;
}) {
  const local = frame - segment.fromFrame;
  const crop = cropAt(segment.crop, local);
  const insert =
    segment.detailInsert &&
    local >= segment.detailInsert.fromFrame &&
    local < segment.detailInsert.toFrame
      ? segment.detailInsert
      : null;
  const transform = insert
    ? {
        x:
          insert.center[0] -
          (insert.rect.x + insert.rect.width / 2) * insert.scale,
        y:
          insert.center[1] -
          (insert.rect.y + insert.rect.height / 2) * insert.scale,
        scale: insert.scale,
      }
    : crop;
  const sourceSeconds = ((segment.sourceStartFrame || 0) + local) / 30;
  const pointer = segment.recordedPointer;
  const eventSeconds =
    sourceSeconds - (pointer?.eventToVideoOffsetSeconds || 0);
  const events = pointer?.events || [];
  const position = [...events]
    .reverse()
    .find((e) => e.elapsedSeconds <= eventSeconds);
  const down = [...events]
    .reverse()
    .find(
      (e) =>
        e.type === "pointerdown" &&
        e.button === 0 &&
        e.elapsedSeconds <= eventSeconds,
    );
  const showPointer =
    pointer &&
    position &&
    sourceSeconds >= pointer.fromSourceSeconds &&
    sourceSeconds < pointer.toSourceSeconds;
  return (
    <AbsoluteFill
      style={{
        clipPath: `inset(${crop.insetY}px ${crop.insetX}px)`,
        background: insert?.matte,
      }}
    >
      <AbsoluteFill
        style={{
          transform: `translate(${transform.x}px,${transform.y}px) scale(${transform.scale})`,
          transformOrigin: "0 0",
          clipPath: insert
            ? `inset(${insert.rect.y}px ${1920 - insert.rect.x - insert.rect.width}px ${1080 - insert.rect.y - insert.rect.height}px ${insert.rect.x}px)`
            : undefined,
        }}
      >
        {segment.kind === "video" ? (
          <Sequence
            name={segment.id}
            from={segment.fromFrame - offset}
            durationInFrames={segment.durationFrames}
          >
            <OffthreadVideo
              src={staticFile(segment.src)}
              trimBefore={segment.sourceStartFrame || 0}
              muted
              style={{ width: 1920, height: 1080 }}
            />
          </Sequence>
        ) : (
          <Img
            src={staticFile(segment.src)}
            style={{ width: 1920, height: 1080 }}
          />
        )}
        {showPointer && (
          <svg
            width={1920}
            height={1080}
            style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
          >
            {down && eventSeconds - down.elapsedSeconds < 0.19 && (
              <circle
                cx={down.x}
                cy={down.y - 10}
                r={21}
                fill="none"
                stroke="#aa8cff"
                strokeWidth={3}
              />
            )}
            <g
              transform={`translate(${position.x - 5} ${position.y - 3}) scale(${38 / 32} ${45 / 38})`}
              style={{ filter: "drop-shadow(0 2px 2px #0008)" }}
            >
              <path
                d="M3 2 L3 29 L10 22 L16 35 L22 32 L16 20 L27 20 Z"
                fill="white"
                stroke="#171a22"
                strokeWidth={2}
                strokeLinejoin="round"
              />
            </g>
          </svg>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
}

function NativeShot({
  segment,
  frame,
}: {
  segment: NativeSegment;
  frame: number;
}) {
  const local = frame - segment.fromFrame,
    view = cameraAt(segment.camera, local);
  const evidence = segment.measurement ? contactGeometry(segment.scene) : null;
  if (
    evidence &&
    Math.abs(evidence.distance - segment.measurement!.distance) > 1e-6
  )
    throw new Error("Editorial distance is not the new source pose distance.");
  const anchor = evidence ? project(evidence.midpoint, view) : null;
  const labelOpacity =
    ramp(local, 12, 24) *
    (1 - ramp(local, segment.durationFrames - 12, segment.durationFrames));
  return (
    <AbsoluteFill>
      <MolecularWorld
        scene={segment.scene}
        view={view}
        contactOpacity={segment.contactOpacity || 0}
      />
      {segment.title && (
        <Interactive.Div
          name="CDK2 design question"
          style={{
            position: "absolute",
            left: 112,
            top: 212,
            width: 740,
            fontSize: 84,
            fontWeight: 500,
            letterSpacing: -3.2,
            lineHeight: 1.05,
            opacity: labelOpacity,
          }}
        >
          {segment.title}
        </Interactive.Div>
      )}
      {evidence && anchor && (
        <AbsoluteFill style={{ opacity: labelOpacity }}>
          <svg
            width={1920}
            height={1080}
            style={{ position: "absolute", inset: 0 }}
          >
            {[evidence.donor, evidence.acceptor].map((p, i) => {
              const s = project(p, view);
              return (
                <circle
                  key={i}
                  cx={s[0]}
                  cy={s[1]}
                  r={19}
                  fill="none"
                  stroke="#b0ecdb"
                  strokeWidth={1.5}
                />
              );
            })}
            <path
              d={`M ${anchor[0]} ${anchor[1] - 22} L ${anchor[0]} ${anchor[1] - 64}`}
              stroke="#b0ecdb"
              strokeWidth={1.5}
            />
          </svg>
          <Interactive.Div
            name="Verified computed contact"
            style={{
              position: "absolute",
              left: anchor[0] - 380,
              top: anchor[1] - 343,
              width: 760,
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 34, color: "#cad6e5" }}>
              Computed contact distance
            </div>
            <div
              style={{
                fontSize: 108,
                lineHeight: 1.1,
                marginTop: 16,
                color: "#b0ecdb",
                fontWeight: 500,
                letterSpacing: -4,
              }}
            >
              {evidence.distance.toFixed(2)} Å
            </div>
            <div style={{ fontSize: 28, marginTop: 12, color: "#c9d6e3" }}>
              {segment.measurement!.atomLabel}
            </div>
          </Interactive.Div>
          <div
            style={{
              position: "absolute",
              left: 96,
              bottom: 70,
              fontSize: 28,
              color: "#a8b7c9",
            }}
          >
            Computed pose · CDK2 / {segment.scene.record.candidateName}
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
}

export function validateSource(source: VerifiedSourceV8) {
  if (source.status !== "verified-live-capture")
    throw new Error("V8 cannot render before live capture verification.");
  if (source.sourceRasterVerified !== true)
    throw new Error(
      "Decoded source content bounds must be verified, not only video dimensions.",
    );
  if (
    source.experimentId !== source.submittedExperimentId ||
    source.experimentId !== source.exportedExperimentId
  )
    throw new Error(
      "Submission, result and export must belong to one experiment.",
    );
  if (
    !source.captureManifestSha256 ||
    source.captureManifestSha256.length !== 64
  )
    throw new Error("A verified source manifest hash is required.");
  for (const shot of source.native) {
    if (shot.scene.record.experimentId !== source.experimentId)
      throw new Error("Native geometry comes from a different experiment.");
    if (
      shot.measurement &&
      (shot.scene.record.poseId !== source.poseId ||
        shot.scene.record.candidateId !== source.candidateId)
    )
      throw new Error(
        "Native evidence differs from the inspected candidate/pose.",
      );
  }
}

/** Source assets are required props. There is no demo or previous-film fallback. */
export function LiveFilmV8({
  source,
  offset = 0,
}: {
  source: VerifiedSourceV8;
  offset?: number;
}) {
  validateSource(source);
  const local = useCurrentFrame(),
    frame = local + offset;
  const closing = ramp(
    frame,
    source.closingFromFrame,
    source.closingFromFrame + 24,
  );
  return (
    <FilmFrame dark>
      <AbsoluteFill style={{ background: "#10151e", color: "#f7f8fc" }}>
        <AbsoluteFill
          style={{
            background:
              "radial-gradient(ellipse at 48% 55%,#253149 0%,#141b28 45%,#0d121a 85%)",
          }}
        />
        {source.native
          .filter(
            (s) =>
              frame >= s.fromFrame && frame < s.fromFrame + s.durationFrames,
          )
          .map((s) => (
            <NativeShot key={s.id} segment={s} frame={frame} />
          ))}
        {source.segments
          .filter(
            (s) =>
              frame >= s.fromFrame && frame < s.fromFrame + s.durationFrames,
          )
          .map((s) => (
            <RecordedClip
              key={s.id}
              segment={s}
              frame={frame}
              offset={offset}
            />
          ))}
        {source.overlays
          .filter(
            (s) =>
              frame >= s.fromFrame && frame < s.fromFrame + s.durationFrames,
          )
          .map((s, i) => {
            const age = frame - s.fromFrame,
              opacity =
                ramp(age, 0, 8) *
                (1 - ramp(age, s.durationFrames - 8, s.durationFrames));
            return (
              <Interactive.Div
                key={i}
                name={s.text}
                style={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  ...(s.position === "top" ? { top: 0 } : { bottom: 0 }),
                  padding:
                    s.position === "top" ? "52px 96px 86px" : "86px 96px 52px",
                  background:
                    s.position === "top"
                      ? "linear-gradient(180deg,#10151ef2,#10151eb8,transparent)"
                      : "linear-gradient(0deg,#10151ef2,#10151eb8,transparent)",
                  textAlign: "center",
                  fontSize: 64,
                  fontWeight: 500,
                  letterSpacing: -1.5,
                  lineHeight: 1.15,
                  color: "#f7f8fc",
                  textShadow: "0 2px 14px #000",
                  opacity,
                }}
              >
                {s.text}
                {s.secondary && (
                  <div
                    style={{
                      fontSize: 32,
                      marginTop: 12,
                      color: "#c1cede",
                      letterSpacing: 0,
                    }}
                  >
                    {s.secondary}
                  </div>
                )}
              </Interactive.Div>
            );
          })}
        {frame >= source.closingFromFrame && (
          <AbsoluteFill style={{ opacity: closing }}>
            <AbsoluteFill
              style={{
                background:
                  "radial-gradient(ellipse at center,#10151e77,transparent 75%)",
              }}
            />
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: 361,
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                gap: 30,
                fontSize: 142,
                fontWeight: 600,
                letterSpacing: -6,
              }}
            >
              <Img
                src={staticFile("capychem-mark.png")}
                style={{ width: 148, height: 148 }}
              />
              capychem
            </div>
            <div
              style={{
                position: "absolute",
                top: 554,
                left: 0,
                right: 0,
                textAlign: "center",
                fontSize: 62,
                letterSpacing: -0.8,
                color: "#c1cede",
              }}
            >
              Run the CDK2 example.
            </div>
            <div
              style={{
                position: "absolute",
                bottom: 150,
                left: 0,
                right: 0,
                textAlign: "center",
                fontSize: 40,
                color: "#e4bd66",
              }}
            >
              github.com/ogngnaoh/capychem
            </div>
          </AbsoluteFill>
        )}
      </AbsoluteFill>
    </FilmFrame>
  );
}
