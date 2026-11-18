import {
  AbsoluteFill,
  Easing,
  Freeze,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import type { ReactNode } from "react";
import { FilmFrame } from "../components/Frame";
import { validateSource } from "../v8/LiveFilm";
import { MolecularWorld, contactGeometry } from "../v8/MolecularWorld";
import raw from "../v8/source.json";
import type { Point, VerifiedSourceV8, View } from "../v8/types";

const source = raw as unknown as VerifiedSourceV8;
validateSource(source);
const measurement = source.native.find((shot) => shot.measurement)!;
const scene = measurement.scene;
const contact = contactGeometry(scene);
const path = source.segments.find((shot) => shot.kind === "video")!.src;
const paper = "#efeef3";
const ink = "#171622";
const pocket = "#0f141b";
const W = 1920;
const H = 1080;
export const spatialFrames = 840;

type Rect = { x: number; y: number; w: number; h: number };
type Camera2D = { x: number; y: number; k: number };
const rect = (x: number, y: number, w: number, h: number): Rect => ({
  x,
  y,
  w,
  h,
});
const aim = (x: number, y: number, k: number): Camera2D => ({ x, y, k });
const page = rect(72, 40, 1776, 999);
const withRail = rect(72, 42, 1776, 817);
const leftPose = rect(72, 55, 1084, 819);
const closeup = aim(979, 646, 1.54);
const viewer = rect(320, 140, 1280, 940);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const ease = Easing.bezier(0.43, 0, 0.12, 1);
const move = (v: number, a: number, b: number) =>
  interpolate(v, [a, b], [0, 1], {
    easing: ease,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
const mixRect = (a: Rect, b: Rect, t: number) =>
  rect(
    lerp(a.x, b.x, t),
    lerp(a.y, b.y, t),
    lerp(a.w, b.w, t),
    lerp(a.h, b.h, t),
  );
const mixAim = (a: Camera2D, b: Camera2D, t: number) =>
  aim(lerp(a.x, b.x, t), lerp(a.y, b.y, t), lerp(a.k, b.k, t));
const mixPoint = (a: Point, b: Point, t: number) =>
  a.map((v, i) => lerp(v, b[i], t)) as Point;
const mixView = (a: View, b: View, t: number): View => ({
  eye: mixPoint(a.eye, b.eye, t),
  target: mixPoint(a.target, b.target, t),
  fov: lerp(a.fov, b.fov, t),
  offset: [
    lerp(a.offset?.[0] ?? 0, b.offset?.[0] ?? 0, t),
    lerp(a.offset?.[1] ?? 0, b.offset?.[1] ?? 0, t),
  ],
});

// The archived match-camera is registered to an editorial 1.25x crop.
// Undo that crop to project into the original 1920 x 1080 browser coordinates.
const matched: View = {
  ...measurement.camera[0].view,
  fov:
    (2 *
      Math.atan(
        1.25 * Math.tan((measurement.camera[0].view.fov * Math.PI) / 360),
      ) *
      180) /
    Math.PI,
  offset: [0, 71],
};

function Pixels({ trim }: { trim: number }) {
  return (
    <OffthreadVideo
      src={staticFile(path)}
      trimBefore={trim}
      muted
      style={{ display: "block", width: W, height: H }}
    />
  );
}

function transformFor(area: Rect, target: Camera2D) {
  const scale = Math.max(target.k, area.w / W, area.h / H);
  const x = Math.max(
    0,
    Math.min(W - area.w / scale, target.x - area.w / (2 * scale)),
  );
  const y = Math.max(
    0,
    Math.min(H - area.h / scale, target.y - area.h / (2 * scale)),
  );
  return { scale, x: area.x - x * scale, y: area.y - y * scale };
}

function Window({
  area,
  target,
  children,
  radius = 20,
}: {
  area: Rect;
  target: Camera2D;
  children: ReactNode;
  radius?: number;
}) {
  const { x, y, scale } = transformFor(area, target);
  return (
    <div
      style={{
        position: "absolute",
        left: area.x,
        top: area.y,
        width: area.w,
        height: area.h,
        overflow: "hidden",
        borderRadius: radius,
        background: pocket,
      }}
    >
      <div
        style={{
          position: "absolute",
          width: W,
          height: H,
          transformOrigin: "0 0",
          transform: `translate(${x - area.x}px,${y - area.y}px) scale(${scale})`,
        }}
      >
        {children}
      </div>
    </div>
  );
}

function Plate({
  trim,
  area = page,
  from,
  to,
  during = [0, 1],
}: {
  trim: number;
  area?: Rect;
  from: Camera2D;
  to?: Camera2D;
  during?: [number, number];
}) {
  const frame = useCurrentFrame(),
    cam = mixAim(from, to ?? from, move(frame, ...during));
  return (
    <Window area={area} target={cam}>
      <Pixels trim={trim} />
    </Window>
  );
}

function Rail({
  line,
  detail,
  opacity = 1,
}: {
  line: string;
  detail?: string;
  opacity?: number;
}) {
  return (
    <div
      style={{
        position: "absolute",
        left: 92,
        right: 92,
        bottom: 76,
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        gap: 36,
        color: ink,
        opacity,
      }}
    >
      <div
        style={{
          fontSize: 77,
          fontWeight: 500,
          letterSpacing: "-.056em",
          lineHeight: 1.02,
        }}
      >
        {line}
      </div>
      {detail && (
        <div
          style={{
            fontSize: 37,
            fontWeight: 500,
            letterSpacing: "-.024em",
            color: "#5b566a",
            textAlign: "right",
          }}
        >
          {detail}
        </div>
      )}
    </div>
  );
}

function Opening() {
  const f = useCurrentFrame();
  const register = move(f, 0, 87),
    aperture = move(f, 55, 109);
  const azimuth = lerp(0.82, 0.09, register);
  const radius = lerp(16.2, 18.1, register);
  const center = mixPoint(contact.midpoint, [0, 0, 0], 0.93);
  const focus = mixPoint(center, matched.target, register);
  const swing: View = {
    eye: [
      focus[0] + Math.sin(azimuth) * radius,
      focus[1] + lerp(7.2, -2.14, register),
      focus[2] + Math.cos(azimuth) * radius,
    ],
    target: focus,
    fov: lerp(42, matched.fov, register),
    offset: [0, lerp(-30, 71, register)],
  };
  const view = mixView(swing, matched, move(f, 62, 95));
  // Both layers always share the real browser viewport. Pull the entire page
  // outward; the chrome enters from the edges rather than passing behind 3D.
  const area = mixRect(rect(0, 0, W, 815), page, aperture);
  const framing = mixAim(aim(960, 535, 1.515), aim(960, 540, 0.925), aperture);
  return (
    <>
      <Window area={area} target={framing} radius={20 * aperture}>
        <Freeze frame={0}>
          <Pixels trim={1494} />
        </Freeze>
        <AbsoluteFill
          style={{
            clipPath: `inset(${viewer.y}px ${W - viewer.x - viewer.w}px 0 ${viewer.x}px)`,
            opacity: 1 - move(f, 87, 105),
            background: pocket,
          }}
        >
          <MolecularWorld scene={scene} view={view} contextOpacity={0.2} />
        </AbsoluteFill>
      </Window>
      <div
        style={{
          position: "absolute",
          left: 91,
          right: 90,
          top: 870,
          display: "flex",
          alignItems: "center",
          gap: 24,
          opacity: 1 - move(f, 55, 76),
          transform: `translateY(${move(f, 55, 76) * 24}px)`,
          color: ink,
        }}
      >
        <Img
          src={staticFile("capychem-mark.png")}
          style={{ width: 68, height: 68 }}
        />
        <span
          style={{
            fontSize: 84,
            fontWeight: 500,
            letterSpacing: "-.058em",
            lineHeight: 1,
          }}
        >
          Compare molecular changes in 3D.
        </span>
      </div>
    </>
  );
}

function Setup() {
  const f = useCurrentFrame(),
    arrival = move(f, 0, 16);
  const area = mixRect(page, rect(72, 65, 1776, 940), arrival);
  return (
    <Freeze frame={Math.min(f, 54)}>
      <Plate
        area={area}
        trim={39}
        from={aim(960, 540, 0.925)}
        to={aim(856, 693, 1.9)}
        during={[0, 29]}
      />
    </Freeze>
  );
}

function Submit() {
  const f = useCurrentFrame(),
    push = move(f, 0, 34),
    release = move(f, 48, 64);
  const control = rect(350, 360, 1220, 295);
  const area = mixRect(
    mixRect(rect(72, 65, 1776, 940), control, push),
    withRail,
    release,
  );
  const target = mixAim(
    mixAim(aim(1050, 570, 1.1), aim(1440, 1009, 4.8), push),
    aim(850, 420, 1.13),
    release,
  );
  return (
    <Window area={area} target={target}>
      <Pixels trim={204} />
    </Window>
  );
}

function Elapsed() {
  return (
    <>
      <Plate area={withRail} trim={995} from={aim(723, 330, 1.52)} />
      <Rail line="23 seconds on CPU" detail="Measured run · wait shortened" />
    </>
  );
}

function SelectVariant() {
  const f = useCurrentFrame(),
    pull = move(f, 45, 96);
  return (
    <Window
      area={mixRect(withRail, page, pull)}
      target={mixAim(aim(551, 456, 1.67), aim(960, 540, 0.925), pull)}
    >
      <Pixels trim={1127} />
    </Window>
  );
}

function Inspect() {
  const f = useCurrentFrame();
  const enter = move(f, 0, 16),
    follow = move(f, 26, 75);
  const app = mixRect(page, withRail, follow);
  const cue = mixAim(aim(960, 540, 0.925), aim(1560, 460, 1.6), enter);
  const cam = mixAim(cue, aim(1080, 648, 1.36), follow);
  return (
    <>
      <Window area={app} target={cam}>
        <Pixels trim={1402} />
      </Window>
      {f >= 48 && (
        <Rail
          line="The added group makes contact."
          detail={`${contact.distance.toFixed(2)} Å in this pose`}
          opacity={move(f, 48, 70)}
        />
      )}
    </>
  );
}

function ToolPanel({ x }: { x: number }) {
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: 55,
        width: 668,
        height: 819,
        borderRadius: 20,
        background: pocket,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 22,
          top: 281,
          width: 624,
          height: 244,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            transformOrigin: "0 0",
            transform: "scale(5.6) translate(-1475px,-1024px)",
          }}
        >
          <Pixels trim={1495} />
        </div>
      </div>
    </div>
  );
}

function Export() {
  const f = useCurrentFrame(),
    split = move(f, 0, 34);
  const a = mixRect(withRail, leftPose, split);
  const rail = move(f, 12, 30);
  const x = lerp(1940, 1180, split);
  return (
    <>
      <Window area={a} target={mixAim(aim(1080, 648, 1.36), closeup, split)}>
        <Pixels trim={1495} />
      </Window>
      <ToolPanel x={x} />
      <Rail
        line="Export the selected pose."
        detail="SDF · 3D coordinates"
        opacity={rail}
      />
    </>
  );
}

function Pullback() {
  const f = useCurrentFrame(),
    expand = move(f, 0, 24),
    retreat = move(f, 16, 99);
  const area = mixRect(leftPose, rect(0, 0, W, H), expand);
  const cam = mixAim(closeup, aim(960, 540, 1), expand);
  const target = mixPoint(matched.target, [0, 0, 0], retreat);
  // Revolve as the camera retreats to give the pocket true depth and parallax.
  const theta = lerp(0.08, 0.64, retreat);
  const radius = lerp(17.95, 72, retreat);
  const far: View = {
    eye: [
      target[0] + Math.sin(theta) * radius,
      target[1] + lerp(-2.14, 20, retreat),
      target[2] + Math.cos(theta) * radius,
    ],
    target,
    fov: lerp(matched.fov, 43, retreat),
    offset: [0, lerp(71, 0, retreat)],
  };
  const view = mixView(matched, far, move(f, 0, 28));
  const brand = move(f, 81, 107);
  return (
    <>
      {f < 25 && (
        <>
          <Freeze frame={89}>
            <ToolPanel x={area.x + area.w + 24} />
          </Freeze>
          <AbsoluteFill
            style={{
              transform: `translateY(${area.y + area.h - leftPose.y - leftPose.h}px)`,
            }}
          >
            <Rail
              line="Export the selected pose."
              detail="SDF · 3D coordinates"
              opacity={1 - move(f, 2, 19)}
            />
          </AbsoluteFill>
        </>
      )}
      <Window area={area} target={cam} radius={lerp(20, 0, expand)}>
        <AbsoluteFill style={{ background: pocket }}>
          <div style={{ opacity: 1 - move(f, 82, 112) * 0.94 }}>
            <MolecularWorld
              scene={scene}
              view={view}
              contextOpacity={lerp(0.2, 0.46, retreat)}
              contactOpacity={1 - move(f, 26, 68)}
            />
          </div>
          {f < 17 && (
            <AbsoluteFill style={{ opacity: 1 - move(f, 3, 16) }}>
              <Freeze frame={0}>
                <Pixels trim={1584} />
              </Freeze>
            </AbsoluteFill>
          )}
        </AbsoluteFill>
      </Window>
      <AbsoluteFill
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          opacity: brand,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 26,
            transform: `scale(${lerp(0.88, 1, brand)})`,
          }}
        >
          <Img
            src={staticFile("capychem-mark.png")}
            style={{ width: 154, height: 154 }}
          />
          <span
            style={{
              color: "#fbfafc",
              fontSize: 145,
              fontWeight: 600,
              letterSpacing: "-.063em",
              lineHeight: 1,
            }}
          >
            capychem
          </span>
        </div>
      </AbsoluteFill>
    </>
  );
}

export function SpatialLaunch() {
  return (
    <FilmFrame>
      <AbsoluteFill style={{ background: paper }} />
      <Sequence
        name="Orbit into the live pocket"
        from={0}
        durationInFrames={132}
      >
        <Opening />
      </Sequence>
      <Sequence name="Bring two variants" from={132} durationInFrames={65}>
        <Setup />
      </Sequence>
      <Sequence name="Run locally" from={197} durationInFrames={65}>
        <Submit />
      </Sequence>
      <Sequence name="Measured elapsed time" from={262} durationInFrames={40}>
        <Elapsed />
      </Sequence>
      <Sequence name="Choose the extension" from={302} durationInFrames={115}>
        <SelectVariant />
      </Sequence>
      <Sequence
        name="Track the real drag and wheel"
        from={417}
        durationInFrames={85}
      >
        <Plate
          trim={1282}
          from={aim(960, 540, 0.925)}
          to={aim(995, 589, 1.09)}
          during={[36, 81]}
        />
      </Sequence>
      <Sequence name="Follow the contact" from={502} durationInFrames={113}>
        <Inspect />
      </Sequence>
      <Sequence
        name="Export the exact coordinates"
        from={615}
        durationInFrames={90}
      >
        <Export />
      </Sequence>
      <Sequence name="Pull out to CapyChem" from={705} durationInFrames={135}>
        <Pullback />
      </Sequence>
    </FilmFrame>
  );
}
