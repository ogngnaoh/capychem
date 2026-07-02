import { expect, test } from "@playwright/test";

// Opt-in smoke (pnpm --filter web test:e2e) — needs the live stack: Next dev, FastAPI,
// Postgres, harness venv. Drives the real front door (/launch): pick a task from the
// catalog, shrink the budget, start, and wait for a terminal state. jnk3 reloads its
// ~10 MB model per generation, so keep the budget small and the timeout generous.
test("launch a jnk3 run from the hybrid launcher and reach a terminal state", async ({
  page,
}) => {
  await page.goto("/launch");
  await expect(page.getByText("Objective catalog")).toBeVisible();
  // pick jnk3 from the catalog → the editable resolved-plan mirror
  await page.getByRole("button", { name: /jnk3/ }).first().click();
  await expect(page.getByText("Resolved plan")).toBeVisible();
  await page.getByLabel("Oracle-call budget").fill("40");
  await page.getByRole("button", { name: /^Start run$/ }).click();
  await expect(page).toHaveURL(/\/runs\/\d+/);
  await expect(
    page.getByText(/exhausted|max_generations|no_progress|stopped|errored/),
  ).toBeVisible({ timeout: 240000 });
  await expect(page.getByText("errored", { exact: true })).not.toBeVisible();
});
