import { expect, test, type Page } from "@playwright/test";
import {
  forceDark,
  mockApi,
  MANIFEST_EXPLORATORY,
  SNAPSHOT_COLD,
  SNAPSHOT_EXPLORATORY,
  stabilizeForShot,
  stubWebSocket,
  stubWebSocketDrop,
} from "./_fixtures";

// Capture harness for the 07-08 cockpit resilience states + the exploratory run-detail
// (quality badges, population health, downloads/manifest legend, analyzer "composed
// objective" note) at 1280px. Output dir via SHOT_DIR.

const SHOT_DIR = process.env.SHOT_DIR ?? "/tmp";

test("capture cockpit-cold-start at 1280px (no h-scroll)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await stubWebSocket(page);
  await mockApi(page, { snapshot: SNAPSHOT_COLD });
  await page.goto("/runs/284", { waitUntil: "networkidle" });
  await page.getByText(/Waking the model/).waitFor({ timeout: 10_000 });
  await assertNoScroll(page, "cockpit-cold-start");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/cockpit-cold-start.png`, fullPage: true });
});

test("capture cockpit-reconnecting at 1280px (no h-scroll)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await stubWebSocketDrop(page);
  await mockApi(page, { snapshot: SNAPSHOT_COLD });
  await page.goto("/runs/284", { waitUntil: "networkidle" });
  await page.getByText(/Connection lost — reconnecting/).waitFor({ timeout: 10_000 });
  await assertNoScroll(page, "cockpit-reconnecting");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/cockpit-reconnecting.png`, fullPage: true });
});

test("capture run-detail-exploratory (analyzer note + objective legend) at 1280px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page, { snapshot: SNAPSHOT_EXPLORATORY, manifest: MANIFEST_EXPLORATORY });
  await page.goto("/runs/271", { waitUntil: "networkidle" });
  await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
  await page.getByRole("link", { name: /Download lineage \(CSV\)/ }).waitFor({ timeout: 5_000 });
  await page.waitForTimeout(500);
  await assertNoScroll(page, "run-detail-exploratory");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/run-detail-exploratory.png`, fullPage: true });
});

test("capture run-detail-exploratory-dark at 1280px", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await forceDark(page);
  await mockApi(page, { snapshot: SNAPSHOT_EXPLORATORY, manifest: MANIFEST_EXPLORATORY });
  await page.goto("/runs/271", { waitUntil: "networkidle" });
  await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
  await page.waitForTimeout(500);
  await assertNoScroll(page, "run-detail-exploratory-dark");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/run-detail-exploratory-dark.png`, fullPage: true });
});

async function assertNoScroll(page: Page, name: string) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  console.log(`[shot] ${name}: scrollWidth=${scrollWidth} (<= 1280)`);
  expect(scrollWidth, `${name} must not scroll horizontally`).toBeLessThanOrEqual(1280);
}
