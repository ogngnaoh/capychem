import { test } from "@playwright/test";

// Capture harness for the frontend-design critic loop: route-mocks the runs API
// with edge-case fixtures, renders /runs at 1280px, and writes a screenshot the
// critic reads. No Postgres / FastAPI needed. Output path via SHOT_PATH.

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SHOT_PATH = process.env.SHOT_PATH ?? "/tmp/runs-shot.png";

const ago = (ms: number) => new Date(Date.now() - ms).toISOString();
const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

const FIXTURE = [
  // long task name + live running run with mid-range numbers
  {
    run_id: 12,
    task: "troglitazone_rediscovery",
    mutation_strategy: "llm",
    status: "running",
    best_score: 0.6431,
    oracle_calls: 4200,
    budget: 10000,
    started_at: ago(3 * MIN),
  },
  {
    run_id: 11,
    task: "jnk3",
    mutation_strategy: "llm",
    status: "exhausted",
    best_score: 0.8812,
    oracle_calls: 10000,
    budget: 10000,
    started_at: ago(2 * HOUR),
  },
  {
    run_id: 9,
    task: "qed",
    mutation_strategy: "graph_ga",
    status: "plateaued",
    best_score: 0.9377,
    oracle_calls: 3400,
    budget: 10000,
    started_at: ago(26 * HOUR),
  },
  // null best_score + errored status
  {
    run_id: 7,
    task: "sitagliptin_mpo",
    mutation_strategy: "graph_ga",
    status: "errored",
    best_score: null,
    oracle_calls: 120,
    budget: 10000,
    started_at: ago(5 * DAY),
  },
  {
    run_id: 5,
    task: "median2",
    mutation_strategy: "graph_ga",
    status: "stopped",
    best_score: 0.2233,
    oracle_calls: 800,
    budget: 2000,
    started_at: ago(90 * 1000),
  },
  {
    run_id: 2,
    task: "deco_hop",
    mutation_strategy: "llm",
    status: "exhausted",
    best_score: 0.5719,
    oracle_calls: 5000,
    budget: 5000,
    started_at: ago(8 * DAY),
  },
];

test("capture /runs at 1280px", async ({ page }) => {
  await page.route(`${API}/runs**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE),
    });
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/runs", { waitUntil: "networkidle" });
  await page.getByText("jnk3").waitFor({ timeout: 15_000 });
  await page.screenshot({ path: SHOT_PATH, fullPage: true });
});
