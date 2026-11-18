import React, { useLayoutEffect, useMemo } from "react";
import { useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import {
  CatmullRomCurve3,
  PerspectiveCamera,
  Quaternion,
  Vector3,
} from "three";
import type { MolecularScene, Point, View } from "./types";

const centered = (p: number[], origin: Point): Point =>
  p.map((v, i) => v - origin[i]) as Point;

export function contactGeometry(scene: MolecularScene) {
  const atoms = new Map(
    [
      ...scene.record.structure.ligandAtoms,
      ...scene.record.structure.pocketAtoms,
    ].map((a) => [a.id, a]),
  );
  const contact = scene.record.structure.contacts.find(
    (c) => c.id === scene.contactId,
  );
  if (!contact)
    throw new Error(
      "The new film requires an explicitly bound contact from its own live pose.",
    );
  const donorAtom = atoms.get(contact.ligandAtom),
    acceptorAtom = atoms.get(contact.proteinAtom);
  if (!donorAtom || !acceptorAtom)
    throw new Error(
      "Contact endpoints are absent from the bound molecular structure.",
    );
  const donor = centered(donorAtom.position, scene.origin),
    acceptor = centered(acceptorAtom.position, scene.origin);
  const midpoint = donor.map((v, i) => (v + acceptor[i]) / 2) as Point;
  const distance = Math.hypot(...donor.map((v, i) => v - acceptor[i]));
  if (Math.abs(distance - contact.distance) > 1e-6)
    throw new Error(
      "Bound contact coordinates and recorded distance disagree.",
    );
  return { contact, donor, acceptor, midpoint, distance };
}

function Camera({ view }: { view: View }) {
  const camera = useThree((s) => s.camera);
  useLayoutEffect(() => {
    camera.position.set(...view.eye);
    (camera as PerspectiveCamera).fov = view.fov;
    camera.lookAt(...view.target);
    (camera as PerspectiveCamera).setViewOffset(
      1920,
      1080,
      -(view.offset?.[0] || 0),
      -(view.offset?.[1] || 0),
      1920,
      1080,
    );
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
  }, [camera, view]);
  return null;
}

function Rod({
  a,
  b,
  origin,
  color,
  radius = 0.09,
  opacity = 1,
}: {
  a: number[];
  b: number[];
  origin: Point;
  color: string;
  radius?: number;
  opacity?: number;
}) {
  const shape = useMemo(() => {
    const start = new Vector3(...centered(a, origin)),
      end = new Vector3(...centered(b, origin));
    const direction = end.clone().sub(start);
    return {
      position: start.add(end).multiplyScalar(0.5),
      length: direction.length(),
      quaternion: new Quaternion().setFromUnitVectors(
        new Vector3(0, 1, 0),
        direction.normalize(),
      ),
    };
  }, [a, b, origin]);
  return (
    <mesh position={shape.position} quaternion={shape.quaternion}>
      <cylinderGeometry args={[radius, radius, shape.length, 12]} />
      <meshStandardMaterial
        color={color}
        roughness={0.3}
        metalness={0.16}
        transparent={opacity < 1}
        opacity={opacity}
        depthWrite={opacity === 1}
      />
    </mesh>
  );
}

function Backbone({
  scene,
  opacity,
}: {
  scene: MolecularScene;
  opacity: number;
}) {
  const curves = useMemo(() => {
    const segments: Vector3[][] = [];
    let active: Vector3[] = [];
    let previous:
      | (typeof scene.record.structure.backboneAtoms)[number]
      | undefined;
    for (const atom of scene.record.structure.backboneAtoms) {
      const point = new Vector3(...centered(atom.position, scene.origin));
      if (
        previous &&
        (atom.chain !== previous.chain ||
          point.distanceTo(
            new Vector3(...centered(previous.position, scene.origin)),
          ) > 4.8)
      ) {
        if (active.length > 2) segments.push(active);
        active = [];
      }
      active.push(point);
      previous = atom;
    }
    if (active.length > 2) segments.push(active);
    return segments.map(
      (points) => new CatmullRomCurve3(points, false, "centripetal"),
    );
  }, [scene]);
  return (
    <group>
      {curves.map((curve, i) => (
        <mesh key={i}>
          <tubeGeometry
            args={[
              curve,
              Math.max(32, curve.points.length * 4),
              0.13,
              6,
              false,
            ]}
          />
          <meshStandardMaterial
            color="#3a6680"
            transparent
            opacity={opacity}
            roughness={0.6}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  );
}

export function project(point: Point, view: View): [number, number] {
  const camera = new PerspectiveCamera(view.fov, 1920 / 1080, 0.1, 200);
  camera.position.set(...view.eye);
  camera.lookAt(...view.target);
  camera.setViewOffset(
    1920,
    1080,
    -(view.offset?.[0] || 0),
    -(view.offset?.[1] || 0),
    1920,
    1080,
  );
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  const p = new Vector3(...point).project(camera);
  return [(p.x + 1) * 960, (1 - p.y) * 540];
}

/** Exact fresh pose and receptor coordinates. Only the editorial camera and materials vary. */
export function MolecularWorld({
  scene,
  view,
  contactOpacity = 0,
  contextOpacity = 0.16,
}: {
  scene: MolecularScene;
  view: View;
  contactOpacity?: number;
  contextOpacity?: number;
}) {
  const { record, origin } = scene;
  const atoms = useMemo(
    () =>
      new Map(
        [...record.structure.ligandAtoms, ...record.structure.pocketAtoms].map(
          (a) => [a.id, a],
        ),
      ),
    [record],
  );
  const geometry = contactOpacity > 0 ? contactGeometry(scene) : null;
  return (
    <ThreeCanvas
      width={1920}
      height={1080}
      camera={{ position: view.eye, fov: view.fov, near: 0.1, far: 200 }}
      gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}
    >
      <Camera view={view} />
      <ambientLight intensity={0.8} />
      <directionalLight position={[4, 8, 9]} intensity={3.2} color="#e7ecff" />
      <directionalLight
        position={[-8, -6, 8]}
        intensity={2.8}
        color="#9e8bcf"
      />
      <directionalLight
        position={[-3, -8, -3]}
        intensity={2.3}
        color="#fae4b7"
      />
      <fog attach="fog" args={["#10151e", 32, 85]} />
      <Backbone scene={scene} opacity={contextOpacity} />
      {record.structure.pocketBonds.map((bond, i) => {
        const a = atoms.get(bond.a),
          b = atoms.get(bond.b);
        if (!a || !b) return null;
        const asp =
          "residueNumber" in a &&
          "residueNumber" in b &&
          a.residueNumber === 86 &&
          b.residueNumber === 86;
        return (
          <Rod
            key={`p${i}`}
            a={a.position}
            b={b.position}
            origin={origin}
            color={asp ? "#a8c8ce" : "#52758d"}
            radius={asp ? 0.065 : 0.025}
            opacity={asp ? 0.8 : contextOpacity * 0.7}
          />
        );
      })}
      {record.structure.pocketAtoms
        .filter((a) => a.residueNumber === 86)
        .map((a) => (
          <mesh key={a.id} position={centered(a.position, origin)}>
            <sphereGeometry args={[0.17, 20, 16]} />
            <meshStandardMaterial
              color={a.element === "O" ? "#dd93a2" : "#a8c8ce"}
              roughness={0.35}
            />
          </mesh>
        ))}
      {record.structure.ligandBonds.map((bond, i) => {
        const a = atoms.get(bond.a)!,
          b = atoms.get(bond.b)!;
        return (
          <Rod
            key={`l${i}`}
            a={a.position}
            b={b.position}
            origin={origin}
            color={
              ("extension" in a && a.extension) ||
              ("extension" in b && b.extension)
                ? "#e4bd66"
                : "#9976df"
            }
          />
        );
      })}
      {record.structure.ligandAtoms.map((a) => (
        <mesh key={a.id} position={centered(a.position, origin)}>
          <sphereGeometry args={[a.element === "S" ? 0.4 : 0.28, 32, 24]} />
          <meshStandardMaterial
            color={a.extension ? "#e4bd66" : "#9976df"}
            roughness={0.24}
            metalness={0.12}
          />
        </mesh>
      ))}
      {geometry &&
        Array.from({ length: 10 }, (_, i) => {
          const a = atoms.get(geometry.contact.ligandAtom)!.position,
            b = atoms.get(geometry.contact.proteinAtom)!.position;
          const at = (t: number) => a.map((v, j) => v + (b[j] - v) * t);
          return (
            <Rod
              key={`c${i}`}
              a={at(i / 10)}
              b={at((i + 0.55) / 10)}
              origin={origin}
              color="#9fe3ca"
              radius={0.025}
              opacity={contactOpacity}
            />
          );
        })}
    </ThreeCanvas>
  );
}
