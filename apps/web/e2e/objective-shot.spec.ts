import { expect, test, type Page } from "@playwright/test";
import { forceDark, mockApi, stabilizeForShot } from "./_fixtures";

// Capture harness for the 07-08 objective builder + seed-import on /launch at 1280px.
// Covers: the composer open in custom mode (2 terms + a transform + a live preview from
// mocked POST /objective/validate), dark, and the benchmark flow with a populated
// seed-import list (exploratory badge surfaced). Output dir via SHOT_DIR.

const SHOT_DIR = process.env.SHOT_DIR ?? "/tmp";

async function openBuilder(page: Page) {
  await page.getByRole("button", { name: /Compose custom objective/ }).click();
  await page.getByText("Compose an objective").waitFor({ timeout: 5_000 });
  // Second term + switch it to SA score (reverse_sigmoid), so ≥2 terms + a transform show.
  await page.getByRole("button", { name: /Add term/ }).click();
  const oracles = page.getByLabel(/Oracle for term/);
  await oracles.nth(1).selectOption("sa_score");
  // Let the debounced preview resolve against the mocked validate endpoint.
  await page.waitForTimeout(900);
}

test("capture objective-builder-light at 1280px (no h-scroll)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page);
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Compose custom objective/ }).waitFor({ timeout: 15_000 });
  await openBuilder(page);
  await assertNoScroll(page, "objective-builder-light");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/objective-builder-light.png`, fullPage: true });
});

test("capture objective-builder-dark at 1280px (no h-scroll)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await forceDark(page);
  await mockApi(page);
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Compose custom objective/ }).waitFor({ timeout: 15_000 });
  await openBuilder(page);
  await assertNoScroll(page, "objective-builder-dark");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/objective-builder-dark.png`, fullPage: true });
});

test("capture seed-import (benchmark + custom seed → exploratory) at 1280px", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page);
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await page.getByLabel("Seed molecules").fill("CCO\nc1ccccc1\nCC(=O)Oc1ccccc1C(=O)O");
  await page.getByText(/3 SMILES parsed/).waitFor({ timeout: 5_000 });
  await assertNoScroll(page, "seed-import");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/seed-import.png`, fullPage: true });
});

async function assertNoScroll(page: Page, name: string) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  console.log(`[shot] ${name}: scrollWidth=${scrollWidth} (<= 1280)`);
  expect(scrollWidth, `${name} must not scroll horizontally`).toBeLessThanOrEqual(1280);
}
