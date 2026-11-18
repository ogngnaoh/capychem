import { expect, test, type Page } from "@playwright/test";
import { createRun, waitForRun } from "./live-helpers";

// Deliberately opt in: this test creates a real persisted local calculation.
// Run the API, science worker and studio first. Only the two failed decision
// writes are intercepted; molecular generation/evaluation is never mocked.
test.skip(
  process.env.CAPYCHEM_E2E_LIVE !== "1",
  "Set CAPYCHEM_E2E_LIVE=1 with the local engine running.",
);

async function decisionWrite(page: Page, action: () => Promise<unknown>) {
  const response = page.waitForResponse(
    (response) =>
      response.url().includes("/decisions/") &&
      response.request().method() === "PATCH",
  );
  await action();
  return response;
}

async function saveNote(page: Page, text: string) {
  await page.getByRole("textbox", { name: "Notes for NU6102" }).fill(text);
  const response = await decisionWrite(page, () =>
    page.getByRole("button", { name: "Save note", exact: true }).click(),
  );
  expect(response.ok()).toBe(true);
}

test("failed pin and pose writes cannot leak into later successful note saves", async ({
  page,
}) => {
  const label = `UI decision regression · ${Date.now()}`;
  const experiment = await createRun(page, label);
  await waitForRun(page, experiment.id);
  const candidates = await (
    await page.request.get(`/api/experiments/${experiment.id}/candidates`)
  ).json();
  const candidate = candidates.items.find(
    (row: { name: string }) => row.name === "NU6102",
  );
  expect(candidate.poses.length).toBeGreaterThan(1);
  const pose = page.getByRole("combobox", { name: "Displayed pose" });
  const values = await pose
    .locator("option")
    .evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value),
    );
  const current = await pose.inputValue();
  const baseline = values.find((value) => value !== current)!;
  expect(
    (await decisionWrite(page, () => pose.selectOption(baseline))).ok(),
  ).toBe(true);
  const decisions = async () => {
    const response = await page.request.get(
      `/api/experiments/${experiment.id}/decisions`,
    );
    expect(response.ok()).toBe(true);
    return (await response.json()).items.find(
      (row: { candidate_id: string }) => row.candidate_id === candidate.id,
    );
  };

  await page.route(
    "**/decisions/*",
    (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Injected pin save failure" }),
      }),
    { times: 1 },
  );
  await page
    .getByRole("button", { name: "Pin to comparison", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Injected pin save failure",
  );
  await expect(
    page.getByRole("button", { name: "Pin to comparison", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Notes", exact: true }).click();
  await saveNote(page, "This note must not retry the failed pin.");
  expect((await decisions()).pinned).toBe(false);
  await page
    .getByRole("button", { name: "Dismiss error", exact: true })
    .click();

  await page.route(
    "**/decisions/*",
    (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Injected pose save failure" }),
      }),
    { times: 1 },
  );
  await pose.selectOption(values.find((value) => value !== baseline)!);
  await expect(page.getByRole("alert")).toContainText(
    "Injected pose save failure",
  );
  await expect(pose).toHaveValue(baseline);
  await saveNote(
    page,
    "This note must preserve the confirmed pose and unpinned decision.",
  );
  const final = await decisions();
  expect(final.pinned).toBe(false);
  expect(final.preferred_pose_id).toBe(baseline);
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Displayed pose" }),
  ).toHaveValue(baseline);
  await expect(
    page.getByRole("button", { name: "Pin to comparison", exact: true }),
  ).toBeVisible();
});
