import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { forceDark, mockApi, SNAPSHOT_COMPLETED } from "./_fixtures";

// Accessibility gate (slice 06-04): runs axe-core across every operator route in
// light + dark at the 1280px target viewport and fails on serious/critical WCAG
// violations. The FastAPI origin is route-mocked (mockApi) so no backend/Postgres/WS
// is needed — the same harness the -shot specs use. A completed snapshot is terminal,
// so /runs/{id} renders the full cockpit without opening a WebSocket.

type Route = { name: string; path: string };

const ROUTES: Route[] = [
  { name: "overview", path: "/" },
  { name: "launch", path: "/launch" },
  { name: "runs", path: "/runs" },
  { name: "run-detail", path: "/runs/281" },
  { name: "compare", path: "/compare?a=281&b=268" },
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
