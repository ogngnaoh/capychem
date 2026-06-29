import { expect, test } from "@playwright/test";

// Opt-in smoke (pnpm --filter web test:e2e) — needs the live stack: Next dev,
// FastAPI, Postgres, harness venv. jnk3 reloads its ~10 MB model per generation,
// so the loop is slower than qed; keep the budget small and the timeout generous.
test("launch a jnk3 run and reach a terminal state", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/Launch an optimization/i)).toBeVisible();
  await page.getByLabel("Oracle-call budget").fill("40");
  await page.getByLabel("Population size").fill("20");
  await page.getByLabel("Offspring / gen").fill("10");
  await page.getByLabel("Plateau window").fill("5");
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(/\/runs\/\d+/);
  await expect(
    page.getByText(/exhausted|max_generations|no_progress|stopped|errored/),
  ).toBeVisible({ timeout: 240000 });
  await expect(page.getByText("errored", { exact: true })).not.toBeVisible();
});
