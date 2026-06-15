# PMO AUC-of-top-10 metric & published Graph-GA baselines

> Purpose: ground-truth reference for milestone `01-harness-reproducibility` — the exact PMO
> AUC-of-top-10 metric (so `packages/core/eval` reimplements it faithfully) and the *published*
> vanilla Graph-GA per-task numbers we diff our reproduction against.
>
> **Source-verified on 2026-06-12** against primary sources only: the NeurIPS 2022 paper PDF
> (OpenReview `yCZRdI0Y7G`, Table 2) and the `wenhao-gao/mol_opt` repo source
> (`main/optimizer.py`, `main/graph_ga/{run.py,hparams_default.yaml}`, `run.py`). No blog summaries.

---

## AUC-of-top-10 metric

**One sentence:** PMO's score is the trapezoidal area under the *running-best top-10 mean oracle
score* plotted against number of oracle calls, sampled every `freq_log = 100` calls, divided by the
`max_oracle_calls = 10000` budget — so it lands in `[0, 1]` because PMO oracle scores are themselves
in `[0, 1]`.

### Exact accumulation rules (verified from `main/optimizer.py`)

- The oracle keeps `mol_buffer`, a dict `{smiles: [score, call_order]}` where `score` is the float
  oracle value and `call_order` is the 1-based ordinal at which that SMILES was first scored
  (`self.mol_buffer[smi] = [float(self.evaluator(smi)), len(self.mol_buffer)+1]`). One entry per
  *distinct* SMILES — the oracle memoizes, so re-scoring a known molecule does **not** advance the
  call count (relevant for our reproduction: budget counts unique oracle calls).
- Defaults (set on the `Oracle` wrapper, not `BaseOptimizer.__init__`): `max_oracle_calls = 10000`,
  `freq_log = 100`. The top-level runner `run.py` exposes `--freq_log` (default `100`) and
  `--patience` (default `5`).
- `top_auc` is called as `top_auc(self.mol_buffer, 10, finish, self.freq_log, self.max_oracle_calls)`
  inside `log_intermediate`, producing the `auc_top10` metric.

### Faithful reproduction of `top_auc` (quoted verbatim from `main/optimizer.py`)

```python
def top_auc(buffer, top_n, finish, freq_log, max_oracle_calls):
    sum = 0
    prev = 0
    called = 0
    # sort buffer ASCENDING by call_order (kv[1][1]) -> chronological replay of when molecules entered
    ordered_results = list(sorted(buffer.items(), key=lambda kv: kv[1][1], reverse=False))
    for idx in range(freq_log, min(len(buffer), max_oracle_calls), freq_log):
        temp_result = ordered_results[:idx]                      # all molecules seen by call `idx`
        temp_result = list(sorted(temp_result, key=lambda kv: kv[1][0], reverse=True))[:top_n]  # best top_n by score
        top_n_now = np.mean([item[1][0] for item in temp_result])
        sum += freq_log * (top_n_now + prev) / 2                 # trapezoid over this freq_log window
        prev = top_n_now
        called = idx
    # final partial trapezoid from last logged point to the true end of the buffer
    temp_result = list(sorted(ordered_results, key=lambda kv: kv[1][0], reverse=True))[:top_n]
    top_n_now = np.mean([item[1][0] for item in temp_result])
    sum += (len(buffer) - called) * (top_n_now + prev) / 2
    # finish=True: pad the remaining budget at the final top_n mean (flat tail to max_oracle_calls)
    if finish and len(buffer) < max_oracle_calls:
        sum += (max_oracle_calls - len(buffer)) * top_n_now
    return sum / max_oracle_calls                                # NORMALIZE by budget -> [0,1]
```

**Notes that matter for an exact reimplementation:**

- **x-axis = call_order, not generation.** Molecules are replayed in the order they were *first
  scored*. The "running best top-10" at call `idx` = the 10 highest scores among the first `idx`
  distinct molecules. This is a *monotone non-decreasing* curve.
- **Trapezoidal integration** with step `freq_log` (100), so the curve is sampled at calls
  100, 200, …; the segment before the first 100 calls implicitly starts from `prev = 0`.
- **Two tail terms:** (1) a partial trapezoid from the last multiple-of-100 up to `len(buffer)`;
  (2) if `finish=True` and the run stopped *early* (buffer shorter than 10000, e.g. plateau/patience
  stop), the metric pads the *remaining* budget at the final top-10 mean — i.e. a method that
  converges early is credited with holding its final score for the unused budget. **Our eval must
  pass `finish=True` for the terminal AUC**, matching how PMO reports final numbers.
- **Normalization:** the single `return sum / max_oracle_calls` is the only normalization in code.
  The paper separately states "The reported values of AUCs are min-max scaled to [0, 1]"
  (§ Experimental setup) — this is consistent, not an *extra* step: PMO oracle scores already live in
  `[0, 1]`, so AUC-of-a-[0,1]-curve over `[0, max_calls]` divided by `max_calls` is already in
  `[0, 1]`. There is **no per-task affine rescaling applied on top of `top_auc`** in the published
  numbers — Table 2 values are the direct `top_auc` outputs (confirmed: e.g. degenerate QED ≈ 0.94
  reflects the raw oracle ceiling 0.948, not a 0→1 stretch).

---

## Published Graph-GA baselines (AUC top-10)

Source for **every** number below: **NeurIPS 2022 PMO paper, Table 2** ("Performance of ten best
performing molecular optimization methods based on mean AUC Top-10 … mean and standard deviation
… from 5 independent runs"), column **"Graph GA"** (assembly = Fragments; Jensen 2019 GB-GA, the
**non-LLM** baseline). OpenReview PDF `id=yCZRdI0Y7G`, page 6. Graph GA is **rank 2 of 25** overall
(behind only REINVENT); its 23-task **Sum = 13.751**.

| Task | Graph-GA AUC top-10 | ±std | Source |
|---|---|---|---|
| **qed** ⟵ CapyChem's wired task | **0.940** | **±0.000** | Table 2, qed row |
| zaleplon_mpo | 0.346 | ±0.032 | Table 2 |
| perindopril_mpo | 0.538 | ±0.009 | Table 2 |
| celecoxib_rediscovery | 0.630 | ±0.097 | Table 2 |
| troglitazone_rediscovery | 0.390 | ±0.016 | Table 2 |
| drd2 | 0.964 | ±0.012 | Table 2 |
| jnk3 | 0.553 | ±0.136 | Table 2 |
| gsk3b | 0.788 | ±0.070 | Table 2 |
| albuterol_similarity | 0.838 | ±0.016 | Table 2 |
| amlodipine_mpo | 0.661 | ±0.020 | Table 2 |
| deco_hop | 0.619 | ±0.004 | Table 2 |
| fexofenadine_mpo | 0.760 | ±0.011 | Table 2 |
| isomers_c7h8n2o2 | 0.862 | ±0.065 | Table 2 |
| isomers_c9h10n2o2pf2cl | 0.719 | ±0.047 | Table 2 |
| median1 | 0.294 | ±0.021 | Table 2 |
| median2 | 0.273 | ±0.009 | Table 2 |
| mestranol_similarity | 0.579 | ±0.022 | Table 2 |
| osimertinib_mpo | 0.831 | ±0.005 | Table 2 |
| ranolazine_mpo | 0.728 | ±0.012 | Table 2 |
| scaffold_hop | 0.517 | ±0.007 | Table 2 |
| sitagliptin_mpo | 0.433 | ±0.075 | Table 2 |
| thiothixene_rediscovery | 0.479 | ±0.025 | Table 2 |
| valsartan_smarts | 0.000 | ±0.000 | Table 2 |
| **Sum (23 tasks)** | **13.751** | — | Table 2, Sum row |

### Which task to reproduce against — headroom guidance

- **QED is a degenerate diff target.** The paper explicitly footnotes: *"QED is likely to have a
  global maximum of 0.948 and even random sampling could reach that value. It is disabled to
  meaningfully distinguish different algorithms."* Graph-GA's QED is `0.940 ± 0.000` — every method
  in Table 2 sits at `0.937–0.941`. Reproducing QED is a good **plumbing smoke test** (tight ±0.000
  std → easy to confirm our pipeline lands near 0.94), but it gives an LLM proposer **near-zero
  headroom to "beat" Graph-GA**, so it's a poor task for the eventual G1 beat-baseline story.
- **Tasks with real headroom** (Graph-GA well below 1.0, so an analyzer-driven proposer can plausibly
  exceed it): `jnk3` (0.553), `median1` (0.294), `median2` (0.273), `sitagliptin_mpo` (0.433),
  `zaleplon_mpo` (0.346), `troglitazone_rediscovery` (0.390), `perindopril_mpo` (0.538),
  `scaffold_hop` (0.517), `thiothixene_rediscovery` (0.479). Note `valsartan_smarts = 0.000` for
  Graph-GA — trivially "beatable" but also pathological (most methods score 0), so not a credible win.
- For milestone 01 (reproduce-and-diff, not beat): use **QED as the reproduction smoke test** since
  CapyChem already wires it and its ±0.000 std makes a mismatch unambiguous; pick a higher-headroom
  task (e.g. `jnk3` or `zaleplon_mpo`) later when the beat-baseline attempt begins (milestone 02+).

---

## Reproduction parameters & gotchas

### Graph-GA hyperparameters (verified, `main/graph_ga/hparams_default.yaml`)

```yaml
population_size: 120
offspring_size: 70
mutation_rate: 0.067
```

That's the **entire** default config — only these three. Crossover rate is implicit (Jensen GB-GA
always attempts crossover per offspring; our `harness/capychem_harness/propose.py` mirrors this:
fitness-weighted parent pair → crossover → probabilistic `mutate(child, mutation_rate)`).

**Gotcha — our harness default mutation_rate differs.** CapyChem's `propose.py` takes `mutation_rate`
from the request payload; the modern caller must pass **0.067** to match the published baseline, not
the `0.01` shown in the `propose.py` docstring example. A mismatched mutation rate will shift AUC.

### Starting population

- **PMO default:** Graph-GA samples its initial `population_size` (120) molecules from the **ZINC 250K**
  dataset (`main/graph_ga/run.py`): if `--smi_file` is given it takes `self.all_smiles[:population_size]`
  (first 120, deterministic); otherwise `np.random.choice(self.all_smiles, population_size)` (random,
  seed-dependent). The repo's default `--smi_file` is `None`, i.e. **random draw from ZINC 250K** unless
  a file is supplied.
- **CapyChem ships a 200-SMILES subset** at `harness/capychem_harness/data/starting_pop.smi` (header
  comments it as "ZINC-derived drug-like sample, via mol_opt"). This is **not** the full ZINC 250K and
  **not** PMO's random 120-from-250K draw. **Consequence:** an exact-to-the-third-decimal QED match to
  `0.940` is unlikely from a different seed population — but because QED's published std is `±0.000` and
  the oracle ceiling is ~0.948, any correct Graph-GA run converges to ≈0.93–0.94 within budget. Treat
  the diff as "lands in the published band," not "bit-identical."

### Seeds & budget

- **Budget:** 10,000 unique oracle calls (`max_oracle_calls = 10000`). Loop stops on budget exhaustion
  OR patience (`--patience` default 5: if top-100 mean improves < `1e-3` over the window, increment
  patience; break when patience reached) — at which point `log_intermediate(finish=True)` pads the AUC
  over the remaining budget.
- **Sampling interval:** `freq_log = 100` (AUC sampled every 100 calls). Changing this changes the
  trapezoid grid and thus the number slightly — keep it at 100.
- **Seeds:** PMO reports **mean ± std over 5 independent runs** (`run.py` `--seed` default `[0]`, but the
  paper runs 5 seeds). GB-GA itself sets **no internal RNG seed** in `main/graph_ga/run.py` — determinism
  comes only from the top-level seed loop feeding `np.random.choice` for the starting population.
  CapyChem's `propose.py` *does* seed `random`/`numpy` per request (`base_seed + gen_index`), which is
  stricter than upstream; fine, but means our single-seed number won't equal the published 5-seed mean
  exactly.

### Recommended diff tolerance

Published QED = `0.940 ± 0.000` (5-seed). Our reproduction differs in: (a) starting population (200-SMILES
subset vs ZINC-250K random 120), (b) single seed vs 5-seed mean, (c) possibly stricter per-gen seeding.
Given QED's ±0.000 published std understates run-to-run spread from *different starting pops*, set a
**reproduction tolerance of ±0.02 absolute AUC** for QED (i.e. accept ≈ 0.92–0.96). That is loose enough
to absorb seed/starting-pop variance yet tight enough to catch a genuinely broken metric or pipeline (a
wrong AUC formula or unmemoized budget typically lands far outside this band). For higher-variance tasks
(e.g. `jnk3` ±0.136, `celecoxib_rediscovery` ±0.097) scale tolerance to **≈ ±1.5–2× the published std**.

---

## Citations (exact)

- **Metric definition & `top_auc` code:** `wenhao-gao/mol_opt`, `main/optimizer.py`, function
  `top_auc(buffer, top_n, finish, freq_log, max_oracle_calls)`; defaults `max_oracle_calls = 10000`,
  `freq_log = 100` set on the `Oracle` wrapper; `mol_buffer[smi] = [score, call_order]`. Call site:
  `log_intermediate` → `"auc_top10": top_auc(self.mol_buffer, 10, finish, self.freq_log, self.max_oracle_calls)`.
  GitHub: https://github.com/wenhao-gao/mol_opt/blob/main/main/optimizer.py
- **Budget / metric / min-max-scaled statement:** PMO paper, "Experimental setup" — *"We limit the
  number of oracle calls to 10000 … AUC … of the top-10 average performance versus oracle calls …
  The reported values of AUCs are min-max scaled to [0, 1]."* OpenReview PDF `id=yCZRdI0Y7G`, p.5–6.
  Also arXiv:2206.12411.
- **QED-is-degenerate footnote:** same paper, footnote 1 — *"QED is likely to have a global maximum of
  0.948 and even random sampling could reach that value. It is disabled to meaningfully distinguish
  different algorithms."*
- **Per-task Graph-GA numbers + Sum (13.751) + Rank 2:** PMO paper **Table 2** ("Performance of ten
  best performing molecular optimization methods based on mean AUC Top-10 … from 5 independent runs"),
  column "Graph GA". OpenReview PDF `id=yCZRdI0Y7G`, p.6. Ranking cross-checked in **Table 3** (Graph GA
  = AUC-Top-10 rank 2). Paper: Gao, Fu, Coley, Sun, "Sample Efficiency Matters: A Benchmark for
  Practical Molecular Optimization," NeurIPS 2022 Datasets & Benchmarks. arXiv:2206.12411.
- **Hyperparameters:** `wenhao-gao/mol_opt`, `main/graph_ga/hparams_default.yaml`
  (`population_size: 120`, `offspring_size: 70`, `mutation_rate: 0.067`).
  https://github.com/wenhao-gao/mol_opt/blob/main/main/graph_ga/hparams_default.yaml
- **Starting-pop sampling & loop/patience:** `main/graph_ga/run.py` (`starting_population =
  self.all_smiles[:population_size]` if `smi_file` else `np.random.choice(...)`; patience-based stop →
  `log_intermediate(finish=True)`). Top-level seed/freq_log/patience defaults: `run.py`
  (`--seed` default `[0]`, `--freq_log` default `100`, `--patience` default `5`, `--smi_file` default `None`).

### Verified vs. unverified

- **Verified against primary source (paper Table 2 / repo source):** the full Graph-GA per-task table,
  Sum = 13.751, rank 2, the `top_auc` implementation, `freq_log=100`, `max_oracle_calls=10000`, the
  three hyperparameters, starting-pop sampling logic, patience/finish behavior, and the min-max/QED notes.
- **`[UNVERIFIED]` / inference, not a quoted number:** the **±0.02 QED tolerance** and the
  **±1.5–2× std** rule are *our* engineering recommendations, not PMO-published values — they are
  reasoned from the published ±std plus our known starting-pop/seed deltas, not lifted from a source.
  The claim that Table 2 numbers carry **no extra affine rescaling beyond `/max_oracle_calls`** is
  inferred from consistency (raw QED ≈ oracle ceiling 0.948, not stretched to 1.0) — strongly supported
  but not stated as a line of code; treat as high-confidence inference. No per-task table from a
  *separate* "Appendix A full results" page was read (this 16-page main PDF carries Table 2's full
  23-task Graph-GA column directly, so the appendix was not needed for these numbers).
