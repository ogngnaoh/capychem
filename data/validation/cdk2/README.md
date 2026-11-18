# CDK2 regression baseline

`growth-v2-baseline-v1.json` records four real API experiments: known controls,
mixed input quality, a strict weight limit, and LibInvent seed 47. It freezes the
preparation, implementation, tool/model identities, requests and measured results.
It is a regression baseline for this curated workflow, not a general docking benchmark.

From the repository root, preview the cases without starting calculations:

```bash
python3 scripts/validate_science_api.py
```

With the local API and worker running, start fresh experiments and audit their
downloaded structures using the isolated science environment:

```bash
python3 scripts/validate_science_api.py --run \
  --api http://127.0.0.1:8001 \
  --science-python .science/cpu/bin/python \
  --output-dir /tmp/capychem-regression-run-1
```

Use the science Python path from your setup manifest if it differs. The output
directory must be new. `--case known` selects one case; repeat `--case` to select
several. Omitting `--science-python` still checks API/report identities, accounting
and artifact hashes, but marks the molecular audit `not_run`: crystal RMSD and
geometry are not independently recomputed. Existing experiments, notes and pins
are never modified. A monitoring timeout leaves the experiment available in the
workspace; it does not label a molecule as a scientific failure.

Read `comparison.json` and the individual case reports:

| Exit | Meaning |
|---|---|
| 0 | Contract checks passed; no scientific review flags in the checks performed |
| 1 | Preflight, transport or execution failed; inspect the saved error |
| 2 | A hard contract or artifact consistency check failed |
| 3 | Scientific review required: a known control, incomplete pose pipeline or changed engine |

Hard checks cover input accounting, exclusions, normalized duplicates, frozen
specifications and exact pose/artifact identity. Scientific checks are separate:
loss of a known contact, geometry failure or held-out RMSD above 2 Å requires
review. The 2 Å limit is a broad pose-recovery tolerance, not an exact replay of
the observed 0.359 Å result. Scores, runtime and generated yield are descriptive;
an extra generated hit is never a regression, and a lower score is not proof of
better binding.

By default, changed engine/model identities stop the comparison. Use
`--allow-engine-change` deliberately to compare an updated implementation; its
identities remain recorded and the result requires review. A changed preparation
needs a new baseline. Review the evidence before creating a new versioned fixture;
the runner never updates the baseline automatically.

The 2.6 KB `1H1S_NU6102_observed.sdf` contains deposited NU6102 heavy-atom
coordinates with Chemical Component Dictionary connectivity. It is read only by
the optional audit **after inference finishes**, never passed into generation or
placement. Its hash and provenance are in the fixture. The receptor was still
chosen from this known holo complex, so the experiment is receptor-informed and
retrospective. Source: [PDB 1H1S](https://www.rcsb.org/structure/1H1S);
archive data are [CC0](https://www.wwpdb.org/about/usage-policies).

## Declared neutral polar series

`neutral-polar-study-v1.json` freezes eight input graphs before their outcomes:
NU6094 and NU6102 controls, plus carboxamide, methylsulfone, hydroxymethyl,
hydroxy, acetamide and nitrile para extensions. Three declared embedding/Vina
seed pairs use the same preparation, limits and scientific criteria. The new
variants have no required-hit assertions. Whole-series reference counts and
runtime are `null` because they were unmeasured when the fixture was frozen.

The same opt-in runner can reproduce these three experiments:

```bash
python3 scripts/validate_science_api.py --run \
  --baseline data/validation/cdk2/neutral-polar-study-v1.json \
  --api http://127.0.0.1:8001 \
  --science-python .science/cpu/bin/python \
  --output-dir /tmp/capychem-neutral-polar-run-1
```

Keep the declaration immutable and store observations separately. Compare
eligible/contact counts across seed pairs, pose geometry, selected state and
score spread. Three successful calculations are not a calibrated probability
of binding. The selected neutral states, especially phenol and sulfonamide
states, do not establish populations at any particular pH.

The first neutral series exposed a preparation-sensitive result: the saved phenol
poses had no Asp86 donor contact, while another OH orientation with unchanged
heavy atoms passed the geometric rule. This does **not** turn the diagnostic
orientation into a predicted hit. New production poses therefore record the
fixed-H policy and a graph-derived warning for O–H groups. The warning says
orientation has not been assessed; it does not claim every OH pose is sensitive.
Old experiment artifacts and hit counts are preserved.

To reproduce the separate, read-only diagnostic after a run completes:

```bash
.science/cpu/bin/python data/validation/cdk2/diagnose_oh_orientation.py \
  --report-directory /path/to/completed/attempt \
  --candidate-name 'Para hydroxy' --candidate-name 'Para hydroxymethyl' \
  --output /tmp/capychem-oh-diagnostic.json
```

It samples six declared OH torsion angles without moving heavy atoms, writing
new structures, or changing selection. Its ligand-only MMFF energies are **not**
binding energies or estimates of rotamer populations in the protein. Use it to
identify a preparation assumption that merits further investigation, not to
replace the recorded result or select a favorable angle.
