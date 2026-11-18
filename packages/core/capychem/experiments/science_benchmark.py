"""Retrospective four-compound CDK2 placement benchmark with held-out ligand coordinates.

The receptor is the known NU6102 holo structure 1H1S. Thus this evaluates
receptor-informed template transfer, not prospective cross-target accuracy.
The tested compound's coordinates never initialize its own generated poses.
P/Q are broader-method controls; R is outside the production para-growth scope.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import prolif as plf
from capychem.experiments.chemistry.conformers import generate
from capychem.experiments.chemistry.geometry import inspect_pose
from capychem.experiments.chemistry.identity import scaffold_query
from capychem.experiments.science import choose_pose
from capychem.experiments.science_config import sha256
from capychem.experiments.science_diagnose import (
    align_receptor,
    read_molecule,
    transform,
    vina_case,
    write_molecule,
)
from posebusters import PoseBusters
from rdkit import Chem
from rdkit.Chem import rdMolAlign
from rdkit.Chem.MolStandardize import rdMolStandardize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", default="194715,41821,61531")
    parser.add_argument("--attempts", type=int, default=16)
    args = parser.parse_args()
    D = args.source_dir
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    p = read_molecule(D / "1H1P_native.sdf")
    pq = scaffold_query(p)
    native: dict[str, Chem.Mol] = {}
    for suffix in "PQRS":
        m = read_molecule(D / f"1H1{suffix}_native.sdf")
        states = (
            [m]
            if m.HasSubstructMatch(pq)
            else [
                t
                for t in rdMolStandardize.TautomerEnumerator().Enumerate(m)
                if t.HasSubstructMatch(pq)
            ]
        )
        assert len(states) == 1
        states[0].SetProp("ccd_atom_names", m.GetProp("ccd_atom_names"))
        native[suffix] = states[0]
    sr = Chem.MolFromPDBFile(str(D / "1H1S_prepared.pdb"), removeHs=False)
    aligned: dict[str, Chem.Mol] = {}
    alignments: dict[str, dict[str, Any]] = {}
    for suffix, m in native.items():
        receptor = Chem.MolFromPDBFile(str(D / f"1H1{suffix}_prepared.pdb"), removeHs=False)
        rot, trans, a = align_receptor(sr, receptor, m)
        aligned[suffix] = transform(m, rot.T, -trans @ rot.T)
        alignments[suffix] = a
    q = aligned["Q"]
    parent_from_q = Chem.Mol(p)
    parent_from_q.RemoveAllConformers()
    conf = Chem.Conformer(p.GetNumAtoms())
    mapping = q.GetSubstructMatch(pq)
    for i, j in enumerate(mapping):
        conf.SetAtomPosition(i, q.GetConformer().GetAtomPosition(j))
    parent_from_q.AddConformer(conf)
    templates = {"P": parent_from_q, "Q": aligned["P"], "R": aligned["Q"], "S": aligned["Q"]}
    source = {
        "P": "NU6094 common 18-atom subgraph",
        "Q": "NU2058 18-atom scaffold",
        "R": "NU6094 24-atom scaffold",
        "S": "NU6094 24-atom scaffold",
    }
    fp = plf.Fingerprint(interactions=["HBDonor", "HBAcceptor"])
    buster = PoseBusters(config="dock")
    report: dict[str, Any] = {
        "scope": (
            "Retrospective receptor-informed test in 1H1S: native NU6102 receptor, "
            "target ligand coordinates excluded from each placement input. "
            "Template sources explicitly exclude each held-out test compound. "
            "No property or contact thresholds tuned. P/Q use different priors; "
            "P/R are outside the production para-growth admission scope."
        ),
        "source_hashes": {
            path.name: sha256(path)
            for path in [
                *(D / f"1H1{s}_native.sdf" for s in "PQRS"),
                *(D / f"1H1{s}_prepared.pdb" for s in "PQRS"),
                D / "1H1S_prepared.pdbqt",
                D / "vina",
            ]
        },
        "alignments": alignments,
        "cases": [],
    }
    for compound in "PQRS":
        template = templates[compound]
        query = scaffold_query(template)
        graph = Chem.MolFromSmiles(Chem.MolToSmiles(native[compound]))
        assert graph.HasSubstructMatch(query)
        tmap = template.GetSubstructMatch(pq)
        names = json.loads(p.GetProp("ccd_atom_names"))
        rings = [
            tmap[i]
            for i, n in enumerate(names)
            if n in {"N1", "C2", "N3", "C4", "C5", "C6", "N7", "C8", "N9"}
        ]
        xyz = template.GetConformer().GetPositions()
        box = {"center": xyz.mean(0).tolist(), "size": (np.ptp(xyz, axis=0) + 18).tolist()}
        for seed in list(map(int, args.seeds.split(","))):
            confs, attempts = generate(
                graph, template, graph.GetSubstructMatch(query), args.attempts, seed
            )
            rows: list[dict[str, Any]] = []
            started = time.perf_counter()
            for i, c in enumerate(confs):
                name = f"{compound}-seed{seed}-conf{i}"
                poses, _ = vina_case(
                    c["molecule"],
                    D / "1H1S_prepared.pdbqt",
                    box,
                    out,
                    name,
                    D / "vina",
                    "local",
                    42,
                    16,
                    "vina",
                )
                for mol, score in poses:
                    path = out / f"{name}.sdf"
                    write_molecule(mol, path)
                    mol = Chem.SDMolSupplier(str(path), removeHs=False)[0]
                    e = inspect_pose(mol, template, sr, D / "1H1S_prepared.pdb", buster, fp, rings)
                    rows.append(
                        {
                            "id": name,
                            "score": score,
                            "rmsd_to_observed_A": rdMolAlign.CalcRMS(
                                Chem.RemoveHs(mol), aligned[compound], maxMatches=1000
                            ),
                            "sdf": path.name,
                            **e,
                        }
                    )
            selected = choose_pose(rows)
            energy = min(rows, key=lambda p: p["score"]) if rows else None
            fields = ["id", "score", "asp86_contact", "review_ready", "rmsd_to_observed_A"]
            case = {
                "compound": compound,
                "in_production_para_growth_scope": compound in {"Q", "S"},
                "template": source[compound],
                "seed": seed,
                "attempts": attempts,
                "poses": rows,
                "seconds": time.perf_counter() - started,
                "selected": {k: selected[k] for k in fields} if selected else None,
                "lowest_energy": {k: energy[k] for k in fields} if energy else None,
                "hits": sum(p["review_ready"] and p["asp86_contact"] for p in rows),
                "best_rmsd": min((p["rmsd_to_observed_A"] for p in rows), default=None),
                "best_eligible_rmsd": min(
                    (p["rmsd_to_observed_A"] for p in rows if p["review_ready"]), default=None
                ),
            }
            report["cases"].append(case)
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(
                json.dumps({k: v for k, v in case.items() if k not in {"poses", "attempts"}}),
                flush=True,
            )


if __name__ == "__main__":
    main()
