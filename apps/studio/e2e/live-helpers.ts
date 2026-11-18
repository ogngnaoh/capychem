import { expect, type Page } from "@playwright/test";
export const NU6102 =
  "NS(=O)(=O)c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6102";
export async function createRun(
  page: Page,
  label: string,
  input = NU6102,
  options?: { maxMolecularWeight?: number },
) {
  await page.goto("/experiments/new");
  await expect(
    page.getByRole("combobox", { name: "Reference preparation" }),
  ).toBeEnabled();
  await page
    .getByRole("combobox", { name: "Reference preparation" })
    .selectOption("cdk2_1h1s_nu6094_v1");
  await page.getByRole("textbox", { name: "Experiment name" }).fill(label);
  await page.getByLabel("Candidates", { exact: true }).fill(input);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Embedding attempts per candidate").fill("4");
  if (options?.maxMolecularWeight)
    await page
      .getByLabel("Maximum molecular weight")
      .fill(String(options.maxMolecularWeight));
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/experiments" &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Run experiment", exact: true })
    .click();
  const result = await response;
  expect(result.ok()).toBe(true);
  return result.json();
}
export async function waitForRun(page: Page, id: string) {
  await expect
    .poll(
      async () => {
        const r = await page.request.get(`/api/experiments/${id}`);
        return (await r.json()).status;
      },
      { timeout: 120000, intervals: [1000, 2000, 3000] },
    )
    .toMatch(/^(completed|completed_with_errors)$/);
  await page.goto(`/experiments/${id}`);
  await expect(
    page.getByRole("heading", { name: "Evidence", exact: true }),
  ).toBeVisible();
}
