import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { MarchingCubes } from "three/addons/objects/MarchingCubes.js";
import "./MolecularViewport.css";

import {
  loadMolecularStructures,
  type StructureId,
  type Vec3,
  type MolecularAtom,
  type MolecularContact,
  type MolecularStructure,
} from "./molecularData";
export type {
  StructureId,
  Vec3,
  MolecularAtom,
  MolecularBond,
  MolecularContact,
  MolecularStructure,
} from "./molecularData";
export { loadMolecularStructures } from "./molecularData";
export type ViewportLayers = {
  pocket: boolean;
  contacts: boolean;
  core: boolean;
  parent: boolean;
};
export type ViewportFocus =
  | { kind: "residue"; residueId: string; nonce: number }
  | { kind: "ligand" | "attachment" | "all"; nonce: number };
export type MolecularSelection = {
  kind: "residue" | "atom" | "attachment";
  structureId: StructureId;
  label: string;
  atomId?: string;
  residueId?: string;
  element?: string;
};
export type MolecularViewportApi = {
  resetCamera: () => void;
  capturePng: () => string;
  focus: (focus: ViewportFocus) => void;
};
export type MolecularViewportProps = {
  structures?: MolecularStructure[];
  structureId?: StructureId;
  layers?: ViewportLayers;
  focus?: ViewportFocus;
  onSelection?: (selection: MolecularSelection) => void;
  onReady?: (api: MolecularViewportApi | null) => void;
};
type Options = { structureId: StructureId; layers: ViewportLayers };
type InternalApi = MolecularViewportApi & {
  update: (options: Options) => void;
};
type Label = {
  element: HTMLButtonElement;
  position: THREE.Vector3;
  offset: [number, number];
};
const DEFAULT_LAYERS: ViewportLayers = {
  pocket: true,
  contacts: true,
  core: true,
  parent: false,
};
const ELEMENT: Record<string, string> = {
  C: "#b7bdcd",
  N: "#8494fc",
  O: "#ed777f",
  S: "#e3b267",
  Cl: "#81baa0",
  F: "#81baa0",
};
const PURPLE = "#8a63f2",
  AMBER = "#edb956",
  CYAN = "#65dbe1";
const point = (p: Vec3) => new THREE.Vector3(...p);

function disposeObject(object: THREE.Object3D) {
  const materials = new Set<THREE.Material>(),
    geometries = new Set<THREE.BufferGeometry>();
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (mesh.geometry) geometries.add(mesh.geometry);
    if (mesh.material)
      (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).forEach(
        (m) => materials.add(m),
      );
  });
  geometries.forEach((g) => g.dispose());
  materials.forEach((m) => m.dispose());
}

/** Display-only renderer. Coordinates, bond topology and contact endpoints come
 * from versioned scientific artifacts; this component does no chemistry. */
export default function MolecularViewport({
  structures,
  structureId = "1H1S",
  layers = DEFAULT_LAYERS,
  focus,
  onSelection,
  onReady,
}: MolecularViewportProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<InternalApi | null>(null);
  const optionsRef = useRef<Options>({ structureId, layers });
  const selectionRef = useRef(onSelection),
    readyRef = useRef(onReady);
  const [error, setError] = useState("");
  const [dataset, setDataset] = useState<MolecularStructure[] | null>(null);
  useEffect(() => {
    let alive = true;
    setError("");
    if (structures) {
      setDataset(structures);
      return;
    }
    loadMolecularStructures()
      .then((data) => {
        if (alive) setDataset(data);
      })
      .catch((error) => {
        if (alive) setError(error.message);
      });
    return () => {
      alive = false;
    };
  }, [structures]);
  selectionRef.current = onSelection;
  readyRef.current = onReady;
  optionsRef.current = { structureId, layers };

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !dataset) return;
    const molecularStructure = (id: StructureId) =>
      dataset.find((s) => s.id === id)!;
    if (!molecularStructure(optionsRef.current.structureId)) {
      setError("No molecular coordinates are available for this candidate.");
      return;
    }
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "low-power",
      });
    } catch {
      setError(
        "3D needs WebGL. The molecular evidence and candidate table remain available.",
      );
      return;
    }
    const canvas = renderer.domElement;
    canvas.className = "molecular-viewport-canvas";
    canvas.tabIndex = 0;
    canvas.setAttribute("role", "img");
    canvas.setAttribute(
      "aria-label",
      "Interactive CDK2 pocket. Drag to rotate, scroll to zoom. Arrow keys rotate, plus and minus zoom, R resets. Select a labeled residue to focus it. Observed structures and computational predictions are labeled separately.",
    );
    host.appendChild(canvas);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x10151e, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(33, 1, 0.1, 200);
    const controls = new OrbitControls(camera, canvas);
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    controls.enableDamping = !reducedMotion;
    controls.dampingFactor = 0.1;
    controls.enablePan = true;
    controls.panSpeed = 0.6;
    controls.rotateSpeed = 0.65;
    controls.zoomSpeed = 0.75;
    controls.minDistance = 8;
    controls.maxDistance = 80;
    scene.add(new THREE.AmbientLight("#e2e8ff", 1.5));
    const key = new THREE.DirectionalLight("#f2eaff", 3.1);
    key.position.set(-12, 16, 22);
    scene.add(key);
    const fill = new THREE.DirectionalLight("#9fd7f5", 1.65);
    fill.position.set(14, 5, 5);
    scene.add(fill);
    const rim = new THREE.DirectionalLight("#abafff", 2.2);
    rim.position.set(4, -10, -15);
    scene.add(rim);
    const world = new THREE.Group();
    scene.add(world);
    const ligandGroup = new THREE.Group(),
      contextGroup = new THREE.Group(),
      residuesGroup = new THREE.Group(),
      contactsGroup = new THREE.Group(),
      parentGroup = new THREE.Group(),
      highlightGroup = new THREE.Group();
    world.add(
      contextGroup,
      residuesGroup,
      ligandGroup,
      contactsGroup,
      parentGroup,
      highlightGroup,
    );
    const labelsLayer = document.createElement("div");
    labelsLayer.className = "molecular-viewport-labels";
    host.appendChild(labelsLayer);
    const tooltip = document.createElement("div");
    tooltip.className = "molecular-viewport-tooltip";
    tooltip.hidden = true;
    host.appendChild(tooltip);
    let labels: Label[] = [],
      pickable: THREE.Object3D[] = [];
    let current = optionsRef.current,
      structure = molecularStructure(current.structureId);
    let selectedResidue: string | null = null;
    let raf = 0,
      dirty = true,
      inView = true,
      disposed = false;
    let tween: {
      start: number;
      fromPosition: THREE.Vector3;
      toPosition: THREE.Vector3;
      fromTarget: THREE.Vector3;
      toTarget: THREE.Vector3;
    } | null = null;
    const homeTarget = new THREE.Vector3();
    const homeSize = new THREE.Vector3();
    let homeDistance = 35;
    const fittedDistance = () => {
      const aspect = Math.max(
        0.3,
        (host.clientWidth || 1) / (host.clientHeight || 1),
      );
      const horizontalFit =
        (homeSize.x * 0.6) /
        (Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * aspect);
      return Math.max(28, homeSize.y * 2.8, homeSize.x * 1.8, horizontalFit);
    };
    const schedule = () => {
      if (!raf && !disposed && inView) raf = requestAnimationFrame(render);
    };
    const mark = () => {
      dirty = true;
      schedule();
    };
    const animateTo = (
      target: THREE.Vector3,
      distance: number,
      resetDirection = false,
    ) => {
      const direction = resetDirection
        ? new THREE.Vector3(0.08, -0.12, 1).normalize()
        : camera.position.clone().sub(controls.target).normalize();
      const destination = target.clone().addScaledVector(direction, distance);
      if (reducedMotion) {
        controls.target.copy(target);
        camera.position.copy(destination);
        controls.update();
        tween = null;
      } else
        tween = {
          start: performance.now(),
          fromPosition: camera.position.clone(),
          toPosition: destination,
          fromTarget: controls.target.clone(),
          toTarget: target.clone(),
        };
      mark();
    };
    const resetCamera = () => {
      selectedResidue = null;
      updateHighlight();
      animateTo(homeTarget, homeDistance, true);
    };
    const material = (color: string, roughness = 0.36, opacity = 1) =>
      new THREE.MeshStandardMaterial({
        color,
        roughness,
        metalness: 0.04,
        transparent: opacity < 1,
        opacity,
        depthWrite: opacity >= 1,
      });
    const clear = (group: THREE.Group) => {
      disposeObject(group);
      group.clear();
    };
    const addBond = (
      group: THREE.Group,
      from: THREE.Vector3,
      to: THREE.Vector3,
      radius: number,
      geometry: THREE.CylinderGeometry,
      mat: THREE.Material,
      data?: MolecularSelection,
    ) => {
      const mesh = new THREE.Mesh(geometry, mat),
        direction = to.clone().sub(from);
      mesh.position.copy(from).add(to).multiplyScalar(0.5);
      mesh.scale.set(radius, direction.length(), radius);
      mesh.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        direction.normalize(),
      );
      group.add(mesh);
      if (data) {
        mesh.userData.selection = data;
        pickable.push(mesh);
      }
      return mesh;
    };
    const select = (selection: MolecularSelection) => {
      if (selection.kind === "residue" && selection.residueId) {
        selectedResidue = selection.residueId;
        updateHighlight();
      }
      selectionRef.current?.(selection);
    };
    const addLabel = (
      text: string,
      position: THREE.Vector3,
      selection: MolecularSelection,
      offset: [number, number] = [0, -24],
      special = false,
    ) => {
      const element = document.createElement("button");
      element.type = "button";
      element.className = `molecular-label${special ? " molecular-label-attachment" : ""}`;
      element.textContent = text;
      element.setAttribute("aria-label", `Focus ${text}`);
      element.addEventListener("click", () => {
        select(selection);
        focusOn(
          selection.kind === "residue"
            ? { kind: "residue", residueId: selection.residueId!, nonce: 0 }
            : { kind: "attachment", nonce: 0 },
        );
      });
      labelsLayer.appendChild(element);
      labels.push({ element, position, offset });
    };
    const updateHighlight = () => {
      clear(highlightGroup);
      if (!selectedResidue) return;
      const atoms = structure.pocketAtoms.filter(
        (a) => a.residueId === selectedResidue,
      );
      if (!atoms.length) return;
      const geometry = new THREE.SphereGeometry(1, 16, 12);
      const glow = new THREE.MeshBasicMaterial({
        color: CYAN,
        transparent: true,
        opacity: 0.11,
        depthWrite: false,
      });
      for (const atom of atoms) {
        const mesh = new THREE.Mesh(geometry, glow);
        mesh.position.copy(point(atom.position));
        mesh.scale.setScalar(0.45);
        highlightGroup.add(mesh);
      }
      mark();
    };
    const buildLigand = () => {
      clear(ligandGroup);
      pickable = pickable.filter((m) => m.parent === residuesGroup);
      const sphere = new THREE.SphereGeometry(1, 24, 18),
        cylinder = new THREE.CylinderGeometry(1, 1, 1, 14);
      const atomMap = new Map(structure.ligandAtoms.map((a) => [a.id, a]));
      const mats = new Map<string, THREE.MeshStandardMaterial>();
      const getMat = (atom: MolecularAtom) => {
        let color = ELEMENT[atom.element] || "#bcc7da";
        if (current.layers.core && atom.element === "C")
          color = atom.extension ? AMBER : PURPLE;
        if (current.layers.core && atom.attachment) color = AMBER;
        if (!mats.has(color)) mats.set(color, material(color));
        return mats.get(color)!;
      };
      for (const atom of structure.ligandAtoms) {
        const selection: MolecularSelection = {
          kind: atom.attachment ? "attachment" : "atom",
          structureId: structure.id,
          label: `${structure.compound} · ${atom.name}`,
          atomId: atom.id,
          element: atom.element,
        };
        const mesh = new THREE.Mesh(sphere, getMat(atom));
        mesh.position.copy(point(atom.position));
        mesh.scale.setScalar(
          atom.element === "S" ? 0.41 : atom.attachment ? 0.37 : 0.32,
        );
        mesh.userData.selection = selection;
        ligandGroup.add(mesh);
        pickable.push(mesh);
      }
      for (const bond of structure.ligandBonds) {
        const a = atomMap.get(bond.a)!,
          b = atomMap.get(bond.b)!,
          pa = point(a.position),
          pb = point(b.position),
          mid = pa.clone().add(pb).multiplyScalar(0.5);
        addBond(ligandGroup, pa, mid, 0.13, cylinder, getMat(a));
        addBond(ligandGroup, mid, pb, 0.13, cylinder, getMat(b));
      }
      const attachment = structure.ligandAtoms.find((a) => a.attachment)!;
      const outline = new THREE.Mesh(
        new THREE.SphereGeometry(0.47, 24, 16),
        new THREE.MeshBasicMaterial({
          color: AMBER,
          wireframe: true,
          transparent: true,
          opacity: 0.18,
          depthWrite: false,
        }),
      );
      outline.position.copy(point(attachment.position));
      ligandGroup.add(outline);
    };
    const buildContext = () => {
      clear(contextGroup);
      clear(residuesGroup);
      pickable = [];
      const chunks: MolecularAtom[][] = [];
      for (const atom of structure.backboneAtoms) {
        const last = chunks[chunks.length - 1];
        if (
          !last ||
          atom.residueNumber! !== last[last.length - 1].residueNumber! + 1 ||
          point(atom.position).distanceTo(
            point(last[last.length - 1].position),
          ) > 5
        )
          chunks.push([atom]);
        else last.push(atom);
      }
      // This trace follows C-alpha positions. It is deliberately not presented
      // as an assigned helix/sheet ribbon or experimental electron density.
      const traceMat = material("#547594", 0.65, 0.2);
      for (const chunk of chunks.filter((c) => c.length > 2)) {
        const curve = new THREE.CatmullRomCurve3(
          chunk.map((a) => point(a.position)),
        );
        contextGroup.add(
          new THREE.Mesh(
            new THREE.TubeGeometry(curve, chunk.length * 6, 0.18, 8, false),
            traceMat,
          ),
        );
      }
      const linePositions: number[] = [],
        atomMap = new Map(structure.pocketAtoms.map((a) => [a.id, a]));
      for (const bond of structure.pocketBonds)
        linePositions.push(
          ...atomMap.get(bond.a)!.position,
          ...atomMap.get(bond.b)!.position,
        );
      contextGroup.add(
        new THREE.LineSegments(
          new THREE.BufferGeometry().setAttribute(
            "position",
            new THREE.Float32BufferAttribute(linePositions, 3),
          ),
          new THREE.LineBasicMaterial({
            color: "#7e98b4",
            transparent: true,
            opacity: 0.17,
            depthWrite: false,
          }),
        ),
      );
      // Soft atomic envelope for spatial context. NOT a solvent-accessible
      // surface, predicted pocket boundary, density map, or energetic field.
      const envelope = new MarchingCubes(
        40,
        new THREE.MeshStandardMaterial({
          color: "#456780",
          roughness: 0.8,
          transparent: true,
          opacity: 0.035,
          depthWrite: false,
          side: THREE.FrontSide,
        }),
        false,
        false,
        65000,
      );
      envelope.scale.setScalar(18);
      for (const atom of structure.pocketAtoms)
        envelope.addBall(
          atom.position[0] / 36 + 0.5,
          atom.position[1] / 36 + 0.5,
          atom.position[2] / 36 + 0.5,
          0.26,
          12,
        );
      envelope.update();
      contextGroup.add(envelope);
      const contactResidues = new Set(
        structure.contacts.map((c) => c.residueId),
      );
      const displayedAtoms = structure.pocketAtoms.filter((a) =>
        contactResidues.has(a.residueId!),
      );
      const ids = new Set(displayedAtoms.map((a) => a.id));
      const sphere = new THREE.SphereGeometry(1, 16, 12),
        cylinder = new THREE.CylinderGeometry(1, 1, 1, 10);
      const mats = new Map<string, THREE.MeshStandardMaterial>();
      const getMat = (a: MolecularAtom) => {
        const color =
          a.element === "C" ? "#879caf" : ELEMENT[a.element] || "#879caf";
        if (!mats.has(color)) mats.set(color, material(color, 0.5));
        return mats.get(color)!;
      };
      for (const atom of displayedAtoms) {
        const selection: MolecularSelection = {
          kind: "residue",
          structureId: structure.id,
          residueId: atom.residueId,
          label: `${atom.residue!.slice(0, 1)}${atom.residue!.slice(1).toLowerCase()}${atom.residueNumber}`,
          atomId: atom.id,
        };
        const mesh = new THREE.Mesh(sphere, getMat(atom));
        mesh.position.copy(point(atom.position));
        mesh.scale.setScalar(0.2);
        mesh.userData.selection = selection;
        residuesGroup.add(mesh);
        pickable.push(mesh);
      }
      for (const bond of structure.pocketBonds)
        if (ids.has(bond.a) && ids.has(bond.b)) {
          const a = atomMap.get(bond.a)!,
            b = atomMap.get(bond.b)!,
            pa = point(a.position),
            pb = point(b.position),
            mid = pa.clone().add(pb).multiplyScalar(0.5);
          addBond(residuesGroup, pa, mid, 0.075, cylinder, getMat(a));
          addBond(residuesGroup, mid, pb, 0.075, cylinder, getMat(b));
        }
    };
    const buildAnnotations = () => {
      clear(contactsGroup);
      clear(parentGroup);
      labels.forEach((l) => l.element.remove());
      labels = [];
      const all = new Map(
        [...structure.ligandAtoms, ...structure.pocketAtoms].map((a) => [
          a.id,
          a,
        ]),
      );
      const residueContacts = new Map<string, MolecularContact[]>();
      for (const contact of structure.contacts) {
        const ligandAtom = all.get(contact.ligandAtom),
          proteinAtom = all.get(contact.proteinAtom);
        if (!ligandAtom || !proteinAtom) continue;
        const from = point(ligandAtom.position),
          to = point(proteinAtom.position);
        const line = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints([from, to]),
          new THREE.LineDashedMaterial({
            color: CYAN,
            dashSize: 0.12,
            gapSize: 0.12,
            transparent: true,
            opacity: 0.86,
            depthWrite: false,
          }),
        );
        line.computeLineDistances();
        contactsGroup.add(line);
        residueContacts.set(contact.residueId, [
          ...(residueContacts.get(contact.residueId) || []),
          contact,
        ]);
      }
      if (current.layers.contacts)
        for (const [residueId, contacts] of residueContacts) {
          const contact = contacts[0],
            atom = all.get(contact.proteinAtom)!;
          const p = point(atom.position),
            offset: [number, number] =
              residueId === "A:86"
                ? [-30, -25]
                : residueId === "A:81"
                  ? [25, 25]
                  : [30, -25];
          addLabel(
            `${contact.residueLabel.toUpperCase()} · ${contact.distance.toFixed(1)} Å`,
            p,
            {
              kind: "residue",
              structureId: structure.id,
              residueId,
              label: contact.residueLabel,
            },
            offset,
          );
        }
      const attachment = structure.ligandAtoms.find((a) => a.attachment)!;
      if (current.layers.core && attachment)
        addLabel(
          attachment.name,
          point(attachment.position),
          {
            kind: "attachment",
            structureId: structure.id,
            atomId: attachment.id,
            label: `${attachment.name} attachment`,
          },
          [8, -30],
          true,
        );
      const parentId = structure.parentStructureId ?? "1H1P";
      if (current.structureId !== parentId && molecularStructure(parentId)) {
        const parent = molecularStructure(parentId),
          map = new Map(parent.ligandAtoms.map((a) => [a.id, a]));
        const positions: number[] = [];
        for (const bond of parent.ligandBonds)
          positions.push(
            ...map.get(bond.a)!.position,
            ...map.get(bond.b)!.position,
          );
        const ghost = new THREE.LineSegments(
          new THREE.BufferGeometry().setAttribute(
            "position",
            new THREE.Float32BufferAttribute(positions, 3),
          ),
          new THREE.LineDashedMaterial({
            color: "#d9dfef",
            dashSize: 0.17,
            gapSize: 0.09,
            transparent: true,
            opacity: 0.6,
            depthWrite: false,
          }),
        );
        ghost.computeLineDistances();
        parentGroup.add(ghost);
      }
      contactsGroup.visible = current.layers.contacts;
      parentGroup.visible = current.layers.parent;
    };
    const rebuild = (initial = false) => {
      structure = molecularStructure(current.structureId);
      selectedResidue = null;
      buildContext();
      buildLigand();
      buildAnnotations();
      updateHighlight();
      contextGroup.visible = current.layers.pocket;
      residuesGroup.visible = current.layers.pocket || current.layers.contacts;
      const endpointIds = new Set(
        structure.contacts.map((contact) => contact.proteinAtom),
      );
      const fitAtoms = [
        ...structure.ligandAtoms,
        ...structure.pocketAtoms.filter((atom) => endpointIds.has(atom.id)),
      ];
      const box = new THREE.Box3().setFromPoints(
        fitAtoms.map((a) => point(a.position)),
      );
      box.getCenter(homeTarget);
      homeTarget.y += 0.4;
      box.getSize(homeSize);
      homeDistance = fittedDistance();
      if (initial) {
        controls.target.copy(homeTarget);
        camera.position
          .copy(homeTarget)
          .add(new THREE.Vector3(2, -3, homeDistance));
        controls.update();
      } else animateTo(homeTarget, homeDistance, true);
      canvas.setAttribute(
        "aria-label",
        `Interactive ${structure.compound} in CDK2, ${structure.origin === "observed" ? "observed reference" : structure.origin === "template" ? "protein-aligned template" : "computed prediction"} ${structure.id}. Drag to rotate, scroll to zoom. Arrow keys rotate, plus and minus zoom, R resets. Select a labeled residue to focus it.`,
      );
      mark();
    };
    const focusOn = (request: ViewportFocus) => {
      if (request.kind === "all") {
        resetCamera();
        return;
      }
      if (request.kind === "ligand") {
        selectedResidue = null;
        updateHighlight();
        animateTo(homeTarget, Math.max(20, homeDistance * 0.78));
        return;
      }
      if (request.kind === "attachment") {
        const a = structure.ligandAtoms.find((atom) => atom.attachment);
        if (!a) return;
        selectedResidue = null;
        updateHighlight();
        animateTo(point(a.position), 19);
        return;
      }
      const residueId = "residueId" in request ? request.residueId : "";
      const atoms = structure.pocketAtoms.filter(
        (a) => a.residueId === residueId,
      );
      if (!atoms.length) return;
      selectedResidue = residueId;
      updateHighlight();
      const contact = structure.contacts.find((c) => c.residueId === residueId);
      const target = contact
        ? point(
            structure.pocketAtoms.find((a) => a.id === contact.proteinAtom)!
              .position,
          )
            .add(
              point(
                structure.ligandAtoms.find((a) => a.id === contact.ligandAtom)!
                  .position,
              ),
            )
            .multiplyScalar(0.5)
        : atoms
            .reduce((sum, a) => sum.add(point(a.position)), new THREE.Vector3())
            .divideScalar(atoms.length);
      animateTo(target, 18);
    };
    const update = (next: Options) => {
      const changedStructure = next.structureId !== current.structureId,
        changedCore = next.layers.core !== current.layers.core,
        changedContacts = next.layers.contacts !== current.layers.contacts;
      current = next;
      if (changedStructure) rebuild();
      else {
        if (changedCore) buildLigand();
        if (changedCore || changedContacts) buildAnnotations();
        contextGroup.visible = current.layers.pocket;
        residuesGroup.visible =
          current.layers.pocket || current.layers.contacts;
        contactsGroup.visible = current.layers.contacts;
        parentGroup.visible = current.layers.parent;
        mark();
      }
    };
    function render(now: number) {
      raf = 0;
      if (disposed || !inView) return;
      if (tween) {
        const t = Math.min(1, (now - tween.start) / 560),
          smooth = 1 - Math.pow(1 - t, 3);
        camera.position.lerpVectors(
          tween.fromPosition,
          tween.toPosition,
          smooth,
        );
        controls.target.lerpVectors(tween.fromTarget, tween.toTarget, smooth);
        dirty = true;
        if (t === 1) tween = null;
      }
      const moved = controls.update();
      if (dirty || moved) {
        renderer.render(scene, camera);
        const width = host!.clientWidth,
          height = host!.clientHeight;
        const occupied: { x: number; y: number; width: number }[] = [];
        for (const label of labels) {
          const projected = label.position.clone().project(camera);
          let x = (projected.x * 0.5 + 0.5) * width + label.offset[0],
            y = (-projected.y * 0.5 + 0.5) * height + label.offset[1];
          const w = label.element.offsetWidth || 112;
          x = Math.max(w / 2 + 8, Math.min(width - w / 2 - 8, x));
          y = Math.max(75, Math.min(height - 52, y));
          for (const previous of occupied)
            if (
              Math.abs(previous.x - x) < (previous.width + w) / 2 + 8 &&
              Math.abs(previous.y - y) < 34
            )
              y += 36;
          occupied.push({ x, y, width: w });
          label.element.style.transform = `translate(${x}px,${y}px) translate(-50%,-50%)`;
          label.element.hidden =
            projected.z > 1 ||
            projected.z < -1 ||
            Math.abs(projected.x) > 1.1 ||
            Math.abs(projected.y) > 1.1;
        }
        dirty = false;
      }
      if (tween || moved) schedule();
    }
    const raycaster = new THREE.Raycaster(),
      pointer = new THREE.Vector2();
    let down: { x: number; y: number } | null = null;
    const picked = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      pointer.set(
        ((e.clientX - r.left) / r.width) * 2 - 1,
        (-(e.clientY - r.top) / r.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      return raycaster.intersectObjects(
        pickable.filter((m) => m.parent?.visible),
        false,
      )[0]?.object.userData.selection as MolecularSelection | undefined;
    };
    const pointerDown = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY };
      tween = null;
      tooltip.hidden = true;
    };
    const pointerMove = (e: PointerEvent) => {
      if (down) {
        canvas.style.cursor = "grabbing";
        return;
      }
      const selection = picked(e);
      canvas.style.cursor = selection ? "pointer" : "grab";
      tooltip.hidden = !selection;
      if (selection) {
        tooltip.textContent = selection.label;
        const r = canvas.getBoundingClientRect();
        tooltip.style.left = `${Math.min(r.width - 140, Math.max(8, e.clientX - r.left + 14))}px`;
        tooltip.style.top = `${Math.max(8, e.clientY - r.top - 28)}px`;
      }
    };
    const pointerUp = (e: PointerEvent) => {
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 5) {
        const selection = picked(e);
        if (selection) select(selection);
      }
      down = null;
      canvas.style.cursor = "grab";
    };
    const pointerLeave = () => {
      down = null;
      tooltip.hidden = true;
    };
    const keyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "r") {
        e.preventDefault();
        resetCamera();
        return;
      }
      const spherical = new THREE.Spherical().setFromVector3(
        camera.position.clone().sub(controls.target),
      );
      if (e.key === "ArrowLeft") spherical.theta -= 0.13;
      else if (e.key === "ArrowRight") spherical.theta += 0.13;
      else if (e.key === "ArrowUp")
        spherical.phi = Math.max(0.12, spherical.phi - 0.13);
      else if (e.key === "ArrowDown")
        spherical.phi = Math.min(Math.PI - 0.12, spherical.phi + 0.13);
      else if (e.key === "+" || e.key === "=")
        spherical.radius = Math.max(8, spherical.radius * 0.9);
      else if (e.key === "-")
        spherical.radius = Math.min(80, spherical.radius * 1.1);
      else return;
      e.preventDefault();
      tween = null;
      camera.position
        .copy(controls.target)
        .add(new THREE.Vector3().setFromSpherical(spherical));
      controls.update();
      mark();
    };
    const resize = () => {
      const width = host.clientWidth || 1,
        height = host.clientHeight || 1;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      if (homeSize.lengthSq()) {
        const previousDistance = homeDistance;
        homeDistance = fittedDistance();
        // Preserve the user's orientation and relative zoom as the canvas narrows.
        camera.position
          .sub(controls.target)
          .multiplyScalar(homeDistance / previousDistance)
          .add(controls.target);
        controls.update();
      }
      mark();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    const intersection = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      if (inView) mark();
    });
    intersection.observe(host);
    controls.addEventListener("change", mark);
    canvas.addEventListener("pointerdown", pointerDown);
    canvas.addEventListener("pointermove", pointerMove);
    canvas.addEventListener("pointerup", pointerUp);
    canvas.addEventListener("pointerleave", pointerLeave);
    canvas.addEventListener("pointercancel", pointerLeave);
    canvas.addEventListener("keydown", keyDown);
    const contextLost = (e: Event) => {
      e.preventDefault();
      setError(
        "The 3D context was interrupted. Reload the page to restore the view; your workspace remains saved.",
      );
    };
    canvas.addEventListener("webglcontextlost", contextLost);
    rebuild(true);
    resize();
    const capturePng = () => {
      renderer.render(scene, camera);
      const output = document.createElement("canvas");
      output.width = canvas.width;
      output.height = canvas.height;
      const context = output.getContext("2d")!;
      context.fillStyle = "#10151e";
      context.fillRect(0, 0, output.width, output.height);
      context.drawImage(canvas, 0, 0);
      const scale = canvas.width / host.clientWidth;
      context.scale(scale, scale);
      const bounds = host.getBoundingClientRect();
      for (const { element } of labels) {
        if (element.hidden) continue;
        const rect = element.getBoundingClientRect(),
          style = getComputedStyle(element);
        const x = rect.left - bounds.left,
          y = rect.top - bounds.top;
        context.fillStyle = style.backgroundColor;
        context.beginPath();
        context.roundRect(x, y, rect.width, rect.height, 5);
        context.fill();
        context.strokeStyle = style.borderColor;
        context.lineWidth = 1;
        context.stroke();
        context.fillStyle = style.color;
        context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText(
          element.textContent || "",
          x + rect.width / 2,
          y + rect.height / 2,
        );
      }
      context.textAlign = "left";
      context.textBaseline = "top";
      context.fillStyle = "#eef2fa";
      context.font = "600 18px sans-serif";
      context.fillText(structure.compound, 20, 18);
      context.fillStyle = "#a4b4cc";
      context.font = "11px sans-serif";
      context.fillText(
        `${structure.origin === "observed" ? "Observed reference" : structure.origin === "template" ? "Protein-aligned template" : "Computed prediction"} · ${structure.id} · receptor ${structure.receptorId}`,
        20,
        44,
      );
      context.fillStyle = "#90a2bd";
      context.font = "9px sans-serif";
      context.fillText(
        "CapyChem · Coordinates in Å · Contact geometry does not establish affinity",
        20,
        host.clientHeight - 24,
      );
      return output.toDataURL("image/png");
    };
    const api: InternalApi = {
      update,
      resetCamera,
      focus: focusOn,
      capturePng,
    };
    apiRef.current = api;
    readyRef.current?.(api);
    return () => {
      disposed = true;
      apiRef.current = null;
      readyRef.current?.(null);
      cancelAnimationFrame(raf);
      observer.disconnect();
      intersection.disconnect();
      controls.removeEventListener("change", mark);
      controls.dispose();
      canvas.removeEventListener("pointerdown", pointerDown);
      canvas.removeEventListener("pointermove", pointerMove);
      canvas.removeEventListener("pointerup", pointerUp);
      canvas.removeEventListener("pointerleave", pointerLeave);
      canvas.removeEventListener("pointercancel", pointerLeave);
      canvas.removeEventListener("keydown", keyDown);
      canvas.removeEventListener("webglcontextlost", contextLost);
      disposeObject(world);
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
      labelsLayer.remove();
      tooltip.remove();
    };
  }, [dataset]);
  useEffect(() => {
    apiRef.current?.update(optionsRef.current);
  }, [structureId, layers.pocket, layers.contacts, layers.core, layers.parent]);
  useEffect(() => {
    if (focus) apiRef.current?.focus(focus);
  }, [focus]);
  return (
    <div
      ref={hostRef}
      className="molecular-viewport"
      data-structure={structureId}
    >
      {error ? (
        <div className="molecular-viewport-error" role="status">
          {error}
        </div>
      ) : !dataset ? (
        <div className="molecular-viewport-error" role="status">
          Loading molecular coordinates…
        </div>
      ) : null}
    </div>
  );
}
