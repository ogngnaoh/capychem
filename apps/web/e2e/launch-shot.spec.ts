import { expect, test } from "@playwright/test";
import { forceDark, mockApi, RESOLUTION_NOMATCH, stabilizeForShot } from "./_fixtures";
import type { Page } from "@playwright/test";

// Capture harness for the REAL hybrid launcher (/launch) at 1280px. Covers the base
// state (catalog + empty mirror), dark, a resolved plan (task picked from the catalog →
// editable mirror + guardrails all-clear), and the grounded FR-015 no-match refusal.
// Route-mocks GET /catalog + POST /intent/resolve. Output dir via SHOT_DIR.

const SHOT_DIR = process.env.SHOT_DIR ?? "/tmp";

test("capture launch-light at 1280px (no h-scroll)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page);
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.waitForTimeout(400);
  await assertNoScroll(page, "launch-light");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/launch-light.png`, fullPage: true });
});

test("capture launch-dark at 1280px (no h-scroll)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await forceDark(page);
  await mockApi(page);
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.waitForTimeout(400);
  await assertNoScroll(page, "launch-dark");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/launch-dark.png`, fullPage: true });
});

test("capture launch-resolved (task picked → mirror) at 1280px", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page);
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  // pick a task from the catalog → the editable resolved-plan mirror appears
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await page.waitForTimeout(300);
  await assertNoScroll(page, "launch-resolved");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/launch-resolved.png`, fullPage: true });
});

test("capture launch-refusal (grounded no-match, FR-015) at 1280px", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page, { resolution: RESOLUTION_NOMATCH });
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByLabel("Describe what you want").fill("make it dissolve well in water");
  await page.getByRole("button", { name: /^Resolve$/ }).click();
  await page.getByText("No benchmark matches that objective").waitFor({ timeout: 5_000 });
  await page.waitForTimeout(300);
  await assertNoScroll(page, "launch-refusal");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/launch-refusal.png`, fullPage: true });
});

test("capture launch-seed-rejected (server 422 marks bad SMILES, A3) at 1280px", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page, { createReject: ["BADSEED"] });
  await page.goto("/launch", { waitUntil: "networkidle" });
  await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
  await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
  await page.getByLabel("Seed molecules").fill("CCO\nBADSEED\nc1ccccc1");
  await page.getByText(/3 SMILES parsed/).waitFor({ timeout: 5_000 });
  await page.getByRole("button", { name: /^Start run$/ }).click();
  // The server names the bad seed; SeedImport marks exactly that token as rejected.
  await page.getByText("rejected").waitFor({ timeout: 5_000 });
  await assertNoScroll(page, "launch-seed-rejected");
  await stabilizeForShot(page);
  await page.screenshot({ path: `${SHOT_DIR}/launch-seed-rejected.png`, fullPage: true });
});

async function assertNoScroll(page: Page, name: string) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  console.log(`[shot] ${name}: scrollWidth=${scrollWidth} (<= 1280)`);
  expect(scrollWidth, `${name} must not scroll horizontally`).toBeLessThanOrEqual(1280);
}
