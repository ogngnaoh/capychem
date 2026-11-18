import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import {
  forceDark,
  MANIFEST_EXPLORATORY,
  mockApi,
  SNAPSHOT_COMPLETED,
  SNAPSHOT_EXPLORATORY,
} from "./_fixtures";

// Accessibility gate: runs axe-core across every operator route in
// light + dark at the 1280px target viewport and fails on serious/critical WCAG
// violations. The FastAPI origin is route-mocked (mockApi) so no backend/Postgres/WS
// is needed. A completed snapshot is terminal,
// so /runs/{id} renders the full cockpit without opening a WebSocket.

type Route = { name: string; path: string };

const ROUTES: Route[] = [
  { name: "overview", path: "/" },
  { name: "launch", path: "/launch" },
  { name: "runs", path: "/runs" },
  { name: "run-detail", path: "/runs/281" },
  { name: "compare", path: "/compare?a=281&b=269" },
];

const THEMES = ["light", "dark"] as const;

for (const route of ROUTES) {
  for (const theme of THEMES) {
    test(`a11y: ${route.name} (${theme}) — no serious/critical axe violations`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      if (theme === "dark") await forceDark(page);
      await mockApi(page, { snapshot: SNAPSHOT_COMPLETED });
      await page.goto(route.path, { waitUntil: "networkidle" });
      // Let the client components settle after their mocked fetches resolve.
      await page.waitForTimeout(800);

      await assertNoHorizontalOverflow(page);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      const blocking = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      const summary = blocking
        .map((v) => `${v.id} (${v.impact}) ×${v.nodes.length}`)
        .join(", ");

      expect(
        blocking,
        `serious/critical a11y violations on ${route.name} (${theme}): ${summary}`,
      ).toEqual([]);
    });
  }
}

// Additional surfaces/states: the objective builder open (custom mode) and the exploratory
// run-detail (quality badges, downloads/manifest legend, analyzer note).
async function assertNoHorizontalOverflow(page: Page) {
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width, "The workspace must fit the tested viewport").toBeLessThanOrEqual(page.viewportSize()!.width);
}

async function axeBlocking(page: Page) {
  await assertNoHorizontalOverflow(page);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const blocking = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  return { blocking, summary: blocking.map((v) => `${v.id} (${v.impact}) ×${v.nodes.length}`).join(", ") };
}

for (const theme of THEMES) {
  test(`a11y: objective builder (${theme}) — no serious/critical axe violations`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    if (theme === "dark") await forceDark(page);
    await mockApi(page);
    await page.goto("/launch", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Compose custom objective/ }).click();
    await page.getByText("Compose an objective").waitFor({ timeout: 5_000 });
    await page.getByRole("button", { name: /Add term/ }).click();
    await page.waitForTimeout(900);

    const { blocking, summary } = await axeBlocking(page);
    expect(blocking, `objective builder (${theme}): ${summary}`).toEqual([]);
  });

  test(`a11y: exploratory run-detail (${theme}) — no serious/critical axe violations`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    if (theme === "dark") await forceDark(page);
    await mockApi(page, { snapshot: SNAPSHOT_EXPLORATORY, manifest: MANIFEST_EXPLORATORY });
    await page.goto("/runs/271", { waitUntil: "networkidle" });
    await page.getByText("Analyzer reasoning").waitFor({ timeout: 15_000 });
    await page.waitForTimeout(800);

    const { blocking, summary } = await axeBlocking(page);
    expect(blocking, `exploratory run-detail (${theme}): ${summary}`).toEqual([]);
  });

  // A3 seed-rejected state: the destructive-tinted "rejected" tokens must stay WCAG-AA.
  test(`a11y: seed-rejected (${theme}) — no serious/critical axe violations`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    if (theme === "dark") await forceDark(page);
    await mockApi(page, { createReject: ["BADSEED"] });
    await page.goto("/launch", { waitUntil: "networkidle" });
    await page.getByText("Objective catalog").waitFor({ timeout: 15_000 });
    await page.getByRole("button", { name: /troglitazone_rediscovery/ }).first().click();
    await page.getByText("Resolved plan").waitFor({ timeout: 5_000 });
    await page.getByLabel("Seed molecules").fill("CCO\nBADSEED\nc1ccccc1");
    await page.getByText(/3 SMILES parsed/).waitFor({ timeout: 5_000 });
    await page.getByRole("button", { name: /^Start run$/ }).click();
    await page.getByText("rejected").waitFor({ timeout: 5_000 });
    // Park the pointer away from the just-clicked button so axe scans the resting UI
    // deterministically (hover now uses the AA-checked `bg-primary-hover` token).
    await page.mouse.move(0, 0);
    await page.waitForTimeout(300);

    const { blocking, summary } = await axeBlocking(page);
    expect(blocking, `seed-rejected (${theme}): ${summary}`).toEqual([]);
  });
}
