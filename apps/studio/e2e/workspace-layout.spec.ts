import { expect, test } from "@playwright/test";

const recordedRun = "/experiments/58c63b90-086a-4cb6-adee-e09657734574?mode=demo&candidate=95595e25-6b90-5e75-9244-2eb3a386ad65";

for (const viewport of [{ width: 1280, height: 720 }, { width: 1366, height: 650 }]) {
  test(`molecular review stays usable at ${viewport.width}×${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(recordedRun);
    await expect(page.locator(".molecular-stage canvas")).toBeVisible();
    await expect(page.getByRole("button", { name: "Para carboxamide", exact: true })).toBeVisible();
    const candidates = await page.locator(".workspace-candidate-slot").boundingBox();
    const molecule = await page.locator(".molecular-stage").boundingBox();
    const evidence = await page.locator(".workspace-evidence-slot").boundingBox();
    expect(candidates).not.toBeNull();
    expect(molecule).not.toBeNull();
    expect(evidence).not.toBeNull();
    expect(Math.abs(molecule!.y - candidates!.y)).toBeLessThan(2);
    expect(molecule!.x).toBeGreaterThan(candidates!.x);
    expect(evidence!.x).toBeGreaterThan(molecule!.x);
    expect(molecule!.y + molecule!.height).toBeLessThanOrEqual(viewport.height);
    const last = await page.getByRole("button", { name: "Para carboxamide", exact: true }).boundingBox();
    const footer = await page.locator(".candidate-panel .table-footer").boundingBox();
    expect(last!.y + last!.height).toBeLessThanOrEqual(footer!.y);
    await page.getByRole("button", { name: /^ASP86 2 contacts/ }).click();
    await expect(page.getByRole("button", { name: /^ASP86 2 contacts/ })).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator(".evidence-panel")).toContainText("3.01");
  });
}
