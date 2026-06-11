import { expect, test } from "@playwright/test";

test("launch a run and reach a terminal state", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Oracle-call budget").fill("40");
  await page.getByLabel("Population size").fill("20");
  await page.getByLabel("Offspring / gen").fill("10");
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(/\/runs\/\d+/);
  await expect(page.getByText(/exhausted|max_generations|no_progress|stopped|errored/)).toBeVisible({ timeout: 120000 });
  await expect(page.getByText("errored", { exact: true })).not.toBeVisible(); // a happy-path smoke run must not error
});
