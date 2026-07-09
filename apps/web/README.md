# CapyChem web (`apps/web`)

The operator workbench for CapyChem — a Next.js 16 (App Router) + React 19 +
TypeScript app that drives the FastAPI backend over REST and a live WebSocket.
It covers the four operator flows: **launch** a run, **watch** it live, **browse**
finished runs, and **compare** two runs side by side.

> Every score shown here is an in-silico benchmark-oracle score. The UI makes no
> claim of real-world drug-discovery efficacy — see the root [`README.md`](../../README.md).

## Prerequisites

- Node 22 LTS + [`pnpm`](https://pnpm.io/)
- The CapyChem API running on `:8000` (see the root README quickstart). Without it,
  the UI loads but every data fetch shows an "unavailable" state.

## Develop

From the repo root (pnpm workspaces):

```bash
pnpm install                 # once, installs the whole workspace
pnpm --filter web dev        # dev server → http://localhost:3000
```

Point the app at the backend with `NEXT_PUBLIC_API_URL` (defaults to
`http://localhost:8000`). The WebSocket connects to that same absolute origin —
it is deliberately **not** proxied through Next.js middleware (App Router WS quirks).

## Scripts

| Command | What it does |
|---|---|
| `pnpm --filter web dev` | Dev server with hot reload |
| `pnpm --filter web build` | Production build |
| `pnpm --filter web lint` | ESLint |
| `pnpm --filter web typecheck` | `tsc --noEmit` |
| `pnpm --filter web test` | Vitest component/logic tests |
| `pnpm --filter web exec playwright test` | Playwright e2e (visual-regression shots + an axe-core a11y gate enforced in CI across all routes) |

## Layout

| Path | What's there |
|---|---|
| `app/` | App Router routes: `/` (Overview), `/launch`, `/runs`, `/runs/[id]` (live), `/compare` |
| `app/globals.css` | Design tokens — a warm cream + coral OKLCH system (Source Serif 4 headings, Inter body) |
| `components/workbench/` | The persistent shell, cockpit, and shared presentational components |
| `components/ui/` | shadcn/ui primitives |
| `lib/api.ts` | Typed REST client + WebSocket URL helpers |
| `e2e/` | Playwright specs — visual-regression shots + `a11y.spec.ts` (the axe-core accessibility gate, enforced in CI) |

## Accessibility

The workbench targets WCAG AA at the 1280px demo viewport. The remediation — sufficient
text/focus contrast, an `aria-live` region announcing live-run progress, `role="alert"`
on async errors, a skip-to-content link, per-route titles, and `aria-sort` on the runs
table — shipped in the milestone-06 accessibility slices (`06-03`, `06-04`), and an
axe-core Playwright gate runs in CI across all routes in light and dark. Keep it green.
