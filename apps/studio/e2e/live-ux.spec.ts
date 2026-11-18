import { expect, test } from "@playwright/test";

function contrast(foreground: string, background: string) {
  const luminance = (color: string) => {
    const channels = color.match(/[\d.]+/g)!.slice(0, 3).map(Number);
    const linear = channels.map((channel) => {
      const value = channel / 255;
      return value <= 0.04045
        ? value / 12.92
        : ((value + 0.055) / 1.055) ** 2.4;
    });
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  };
  const a = luminance(foreground), b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

test("setup text remains readable when the operating system prefers dark mode", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/experiments/new?mode=demo");
  const title = page.getByRole("heading", { name: "New experiment", exact: true });
  await expect(title).toBeVisible();
  const colors = await title.evaluate((element) => ({
    foreground: getComputedStyle(element).color,
    background: getComputedStyle(document.body).backgroundColor,
  }));
  expect(contrast(colors.foreground, colors.background)).toBeGreaterThanOrEqual(4.5);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  const rules = page.getByRole("heading", { name: "Set the rules and budget", exact: true });
  await expect(rules).toBeVisible();
  const rulesColors = await rules.evaluate((element) => ({
    foreground: getComputedStyle(element).color,
    background: getComputedStyle(document.body).backgroundColor,
  }));
  expect(contrast(rulesColors.foreground, rulesColors.background)).toBeGreaterThanOrEqual(4.5);
});

test("a failed export can recover without leaving a workspace error", async ({ page }, testInfo) => {
  const manifest = await (await page.request.get("/data/recorded-experiments.json")).json();
  const record = manifest.experiments.find((item: any) => item.candidates.length > 0);
  await page.goto(`/experiments/${record.experiment.id}/activity?mode=demo`);
  await expect(page.getByRole("heading", { name: /Calculation completed|Completed with calculation errors/ })).toBeVisible();
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Export experiment", exact: true });
  await expect(dialog).toBeVisible();
  await page.route(`**${record.export_url}`, route => route.fulfill({status: 503, body: "Temporarily unavailable"}), {times: 1});
  await dialog.getByRole("button", { name: /^Experiment record/ }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await page.screenshot({path: testInfo.outputPath("export-error.png")});
  const download = page.waitForEvent("download");
  await dialog.getByRole("button", { name: /^Experiment record/ }).click();
  await download;
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Export", exact: true })).toBeFocused();
  await page.screenshot({path: testInfo.outputPath("export-recovered.png")});
});
