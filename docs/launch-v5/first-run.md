# Your first CDK2 design round

**Can a small extension reach a nearby part of a protein?** Supply three related molecules, inspect their calculated positions, then repeat the comparison with different sampling seeds. The useful outcome is a specific next question, with the evidence needed to investigate it.

## The chemistry in one minute

A **protein** is the large structure; here it is CDK2. A **ligand** is the smaller molecule in its pocket. A **pose** is one calculated position and shape of that ligand. **Asp86** names one amino acid in CDK2.

We keep a common molecular core and change a small group on its edge. The goal is a plausible pose that retains a hinge interaction and reaches Asp86. A hydrogen bond is an attractive interaction involving a hydrogen atom and a suitably positioned nearby atom. CapyChem checks the geometry of such contacts; it does not measure their strength. The added group must point in the right direction, so 3D is essential.

## 1. Open the workspace and supply three molecules

Follow the [Quick start](../../README.md#quick-start), then open **http://localhost:5181**. Live calculations need the API, scientific environment and worker. No GPU, cloud account or LLM key is required for this supplied-candidate example.

To look around first, use the [recorded demo](../../README.md#try-the-workspace). It contains saved results and supports inspection, comparisons and exports; it cannot launch new calculations. Continue in live mode for the steps below.

Choose **New experiment**. In **Reference preparation**, select **CDK2 · NU6094 para growth**. Set **Experiment name** to **CDK2 · one small extension** and choose **Evaluate candidates**. Paste these lines into **Candidates**:

```text
c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6094
NS(=O)(=O)c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6102
NC(=O)c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 Para carboxamide
```

Confirm the three names in **Inputs to evaluate**. The text before each name is **SMILES**, a compact description of atom connections; you can paste it without learning the notation first.

- **NU6094:** the parent, our starting comparison.
- **NU6102:** a known comparison molecule with an added sulfonamide group.
- **Para carboxamide:** a supplied variant with a different polar extension.

These inputs are supplied by you. This example does not ask AI to invent them. **Generate variants** is a separate option that uses LibInvent after its optional environment is installed.

## 2. Set the rules and run

Click **Continue**. On **Rules & budget**, use:

| Control | Value | Meaning |
|---|---|---|
| Maximum molecular weight | 450 | Size limit, in g/mol |
| Maximum calculated logP | 4.5 | Limit a calculated preference for oily over watery surroundings |
| Maximum rotatable bonds | 8 | Limit flexibility |
| Formal charge | Neutral · 0 | Fixed by this protocol |
| Maximum unique candidates | 3 | Evaluate these three distinct molecular graphs |
| Embedding attempts per candidate | 16 | Try several starting 3D arrangements |
| Admission time limit | 300 | Seconds after which new candidate work stops being admitted |

Under **Reproducibility settings**, use **Embedding seed 194715** and **Vina seed 42**. Seeds control random choices; saving them makes the setup traceable.

Click **Continue**. In **Review your experiment**, check the names, 1H1S receptor, C20 attachment point and limits. **Edit property limits** and **Edit calculation budget** return to the settings. Click **Run experiment** when the review matches your intent.

**Activity** shows real progress. The admission limit is not an exact completion deadline: admitted work finishes at a safe checkpoint. The freshly captured and audited v5 run with these settings took about 28 seconds on the demonstration machine, excluding installation. That is a measured example, not a promised wait.

## 3. Inspect the molecule and its evidence together

Open **Workspace**. On a desktop, the **Candidates** list stays on the left, the molecule occupies the center, and **Evidence** stays on the right. Select NU6094, then NU6102, then Para carboxamide. **Metrics table** switches to the full comparison table; **Candidate list** returns to the list. On a narrow screen, the **Candidates**, **Molecular view** and **Evidence** links jump between the stacked sections.

For each molecule:

1. Open **Molecular layers** and enable **Parent overlay** to see what changed. The parent is a protein-aligned template, not an observed NU6094–1H1S complex.
2. In **Evidence → Pose**, select **ASP86** if that contact is present. The viewer focuses the saved contact and shows the participating atoms and distances.
3. Read **Geometry** and **Properties** too. “Ready to inspect” means the pose passed the declared review checks, not that the molecule is a good drug.

The pose selector above the molecule opens alternative saved arrangements. **Download selected pose** saves the exact displayed coordinates as SDF. A more negative Vina score does not establish stronger real-world binding.

In the fresh audited ordinary run, all three molecules were ready to inspect; NU6102 and carboxamide had an Asp86 contact, while the parent did not. Follow your own displayed results if they differ. An excluded, failed or unassessed candidate is distinct from an evaluated pose with no contact.

## 4. Keep the comparison and test across seeds

Use **Pin to comparison** in Evidence, or each candidate's pin control, to retain all three. Keep the parent as a control. The bottom actions offer **Compare**, **New round** and **Test across seeds**. Compare reviews the current preferred poses; Test across seeds creates new calculations under a shared fixed setup.

Choose **Test across seeds**. Name the Study **CDK2 · does the contact repeat?** Confirm the three candidate names and their source evidence, then click **Continue**. In **Rules & seeds**, keep the same limits and use:

| Run | Embedding seed | Vina seed |
|---|---:|---:|
| 1 | 194715 | 42 |
| 2 | 41821 | 43 |
| 3 | 61531 | 44 |

Click **Continue**, inspect **Review your study**, then click **Run 3 experiments**. These are ordinary local experiments grouped under one question; the local worker processes them sequentially.

The completed matrix shows **Ready** coverage separately from **Asp86 + ready**. Its counts use the protocol-selected pose in each run, not a pose you later prefer. Click a cell to open its exact saved evidence, then **Back to study** to return.

The fresh audited Study produced **NU6094 0/3, NU6102 3/3 and Para carboxamide 2/3**, with all nine observations ready to inspect. It took about 76 seconds on the demonstration machine. The nine selected structures matched the preserved earlier case; this is a reproduction comparison, not proof of improved binding. Your own outcomes take precedence.

**3/3 is a count across three calculations, not a binding probability or three laboratory confirmations.** Check the atoms too: an Asp86 backbone contact differs from a side-chain contact. For a result such as carboxamide 2/3, open the no-contact cell and inspect how that particular pose differs. Other protein contacts may still be present.

## 5. Record a decision and export its evidence

A Study's exact-pose view is read-only. To write a note, choose **Return to current results**, select the candidate, open **Notes**, write the note and click **Save note**. Confirm that it changes to **Saved**.

A useful note names the evidence and next question: “The known comparison recovers the contact here. Inspect why carboxamide differs across seeds before prioritizing further work.” Use this only if your actual results support it. The note belongs to that candidate in the current member experiment; the Study retains its original calculation evidence.

Choose **Export → Experiment record** for the JSON record. Return to the Study and choose **Export study** for its member records and artifact references. Use **Download selected pose** for coordinates. The JSON exports retain identities and artifact references; they are not a bundle of every molecular file.

You have completed a design-and-review loop: supply a change, calculate possible arrangements, inspect the geometry, check variation across seeds and preserve a decision. The current supported scope is one curated CDK2 series with a fixed receptor and neutral 9H scaffold. It is not an arbitrary-protein docking service or a claim of improved potency.

The [validation overview](../redesign/validation-overview.md) explains the controls and their limits. The [live browser record](../redesign/reliability-v8/system-validation.json) links the filmed comparison to the exported coordinates.
