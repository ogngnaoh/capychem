import { expect, test } from "@playwright/test";

const experimentId = process.env.CAPYCHEM_E2E_STEREO_EXPERIMENT;
const studyId = process.env.CAPYCHEM_E2E_STEREO_STUDY;

test("live ambiguous stereochemistry stays visible beside the exact pose and in exports", async ({ page }) => {
  test.skip(!experimentId, "Requires a completed varied-input experiment with specified and unspecified stereo.");
  const response = await page.request.get(`/api/experiments/${experimentId}/candidates`);
  expect(response.ok()).toBe(true);
  const candidates = (await response.json()).items;
  const ambiguous = candidates.find((c: any) => c.unspecifiedStereochemistry && c.structureId);
  const specified = candidates.find((c: any) => c.name === "Para hydroxyethyl R" && c.structureId);
  expect(ambiguous).toBeTruthy();
  expect(specified).toBeTruthy();
  await page.goto(`/experiments/${experimentId}?candidate=${ambiguous.id}`);
  await expect(page.locator(".molecular-stage canvas")).toBeVisible();
  const warning = page.getByRole("note", { name: "Stereochemistry warning" });
  await expect(warning).toBeVisible();
  await expect(warning).toContainText("Stereochemistry unspecified");
  await expect(warning).toContainText(ambiguous.stereochemistryNote);
  await expect(page.getByText("Calculation details", { exact: false }).first()).toBeVisible();
  const exported = await page.request.get(`/api/experiments/${experimentId}/export`);
  expect(exported.ok()).toBe(true);
  expect(await exported.text()).toContain(ambiguous.stereochemistryNote);
  await page.goto(`/experiments/${experimentId}?candidate=${specified.id}`);
  await expect(page.locator(".stage-heading h2")).toHaveText(specified.name);
  await expect(warning).toHaveCount(0);
});

test("live repeated-seed study flags ambiguous identity before opening a result", async ({ page }) => {
  test.skip(!studyId, "Requires a completed study containing specified and unspecified stereo.");
  const response = await page.request.get(`/api/studies/${studyId}`);
  expect(response.ok()).toBe(true);
  const study = await response.json();
  const ambiguous = study.candidates.find((c: any) => c.observations.some((o: any) => o.unspecified_stereochemistry));
  const specified = study.candidates.find((c: any) => c.name.includes(" R"));
  expect(ambiguous).toBeTruthy();
  expect(specified).toBeTruthy();
  await page.goto(`/studies/${studyId}`);
  const row = page.locator(".study-matrix tbody tr").filter({ has: page.getByRole("rowheader", { name: new RegExp(ambiguous.name) }) });
  await expect(row).toContainText("Stereochemistry unspecified · inspect each prepared state");
  const other = page.locator(".study-matrix tbody tr").filter({ has: page.getByRole("rowheader", { name: new RegExp(specified.name) }) });
  await expect(other).not.toContainText("Stereochemistry unspecified");
  await row.getByRole("link").first().click();
  await expect(page.getByRole("note", { name: "Stereochemistry warning" })).toBeVisible();
  await expect(page.getByLabel("Displayed pose", { exact: true })).toHaveValue(ambiguous.observations[0].selected_pose_id);
});
