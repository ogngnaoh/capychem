# CapyChem

A local 3D workspace for structure-guided molecular design. Start with related molecules, or generate variants of a shared core. Compare their calculated positions inside a protein pocket, inspect which atoms touch, and download the exact pose on screen.

[Watch the 28-second product tour](https://github.com/ogngnaoh/capychem/blob/6d482de562679923daea41d151d2dbded3a22041/assets/demo/v10/capychem-studio-launch.mp4?raw=1) · [Run a live experiment](#run-a-live-experiment)

## Try the recorded workspace

From the repository root, with Node.js 22 and pnpm 11.5.0 installed:

```sh
pnpm install --frozen-lockfile
pnpm studio
```

[Open the example experiment](http://127.0.0.1:5181/experiments/58c63b90-086a-4cb6-adee-e09657734574?mode=demo). Select **NU6094**, then **NU6102**. The second molecule has an added group. Select **ASP86** to see which atoms it reaches in the CDK2 protein, drag to rotate the pocket, then choose **Download selected pose**.

[Open the three-run study](http://127.0.0.1:5181/studies/a73fc517-6425-490a-a921-9ea3e7c0686d?mode=demo). With three different sampling seeds, the selected poses reached Asp86 in **0/3** runs for NU6094, **3/3** for NU6102, and **2/3** for the carboxamide variant. Click the carboxamide run that missed to see the difference. These results describe calculated geometry in a fixed receptor. Measuring binding strength requires experimental data.

**Portable demo.** For a machine with just Python 3 and a WebGL browser, download the `capychem-studio-demo` artifact from a successful [CI run](https://github.com/ogngnaoh/capychem/actions/workflows/ci.yml), extract it, and run `python3 serve.py` from the folder containing that file. Open the printed address. To build the same offline workspace yourself after installing the Node dependencies, run `python3 scripts/package_demo.py`. It writes `dist/capychem-studio-demo.zip`.

## Run a live experiment

The supplied-molecule workflow runs on CPU without API keys. Automatic setup has been validated on Apple silicon macOS with **uv**, **Node.js 22**, **pnpm 11.5.0**, and **PostgreSQL 16+**. From the repository root:

```sh
uv sync --frozen --python 3.12
pnpm install --frozen-lockfile
uv python install 3.11
.venv/bin/python scripts/setup_science.py --python "$(uv python find 3.11)"
.venv/bin/python scripts/dev.py
```

Open [Studio](http://127.0.0.1:5181), choose **New experiment → Evaluate candidates**, select **CDK2 · NU6094 para growth**, and paste these two molecules. Review the rules and launch the experiment.

```text
c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6094
NS(=O)(=O)c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6102
```

The API saves your inputs to PostgreSQL. A separate worker uses RDKit and Meeko to prepare the molecules, AutoDock Vina to calculate poses, PoseBusters to check their geometry, and ProLIF to identify contacts. You can close the tab and return to the saved result. Coordinates and other experiment files live in `.local/artifacts/`.

- **Generate variants** by adding `--with-generator` to the science setup command before starting the launcher. This installs CPU PyTorch and the pinned LibInvent checkpoint (about 90 MB). LibInvent proposes side groups. The worker then evaluates them in the pocket.
- **Use an existing PostgreSQL database** by passing `--database-url` to `scripts/dev.py`. The default launcher keeps its own cluster under `.local/postgres/`.
- **Supply your own Vina executable** with `scripts/setup_science.py --vina-binary /path/to/vina` on platforms without the automatic installer. Use version 1.2.7. The full live workflow above was verified on Apple silicon.

## Development and license

The Studio is in [apps/studio](apps/studio), the API in [apps/api](apps/api), and the experiment engine in [packages/core](packages/core/capychem/experiments). The original PMO benchmark app still runs separately via `make setup` and `make dev`. [Development and testing conventions](AGENTS.md)

CapyChem is [MIT licensed](LICENSE). Bundled software, fonts and scientific inputs retain their own terms. [Studio notices](apps/studio/public/THIRD_PARTY_NOTICES.txt) · [Scientific sources and licenses](data/reference/cdk2/THIRD_PARTY_NOTICES.txt)
