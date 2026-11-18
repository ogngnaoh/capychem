import { expect, test, type Page } from "@playwright/test";
import { createRun, waitForRun } from "./live-helpers";

test.skip(process.env.CAPYCHEM_E2E_LIVE !== "1", "Requires the local engine.");

type Decision = {
  candidate_id?: string;
  pinned: boolean;
  notes: string;
  preferred_pose_id: string | null;
  revision: number;
};

async function save(page: Page) {
  const response = page.waitForResponse(
    (r) => r.url().includes("/decisions/") && r.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Save note", exact: true }).click();
  return response;
}

test("two tabs preserve a stale note draft and require an explicit conflict retry", async ({
  page,
  context,
}) => {
  test.setTimeout(180_000);
  const id =
    process.env.CAPYCHEM_E2E_EXISTING_EXPERIMENT ||
    (await createRun(page, `Two-tab conflict · ${Date.now()}`)).id;
  await waitForRun(page, id);
  const candidates = await (
    await page.request.get(`/api/experiments/${id}/candidates`)
  ).json();
  const candidate = candidates.items.find(
    (row: { name: string }) => row.name === "NU6102",
  );
  expect(candidate).toBeTruthy();
  const decisionsPath = `/api/experiments/${id}/decisions`;
  const initial = await (await page.request.get(decisionsPath)).json();
  const original: Decision = initial.items.find(
    (row: Decision) => row.candidate_id === candidate.id,
  ) || { pinned: false, notes: "", preferred_pose_id: null, revision: 0 };
  const current = async (): Promise<Decision> => {
    const response = await page.request.get(decisionsPath);
    expect(response.ok()).toBe(true);
    return (
      (await response.json()).items.find(
        (row: Decision) => row.candidate_id === candidate.id,
      ) || original
    );
  };
  const second = await context.newPage();
  // Freeze only the second tab's reads, simulating a stale tab. Both writes go
  // through the real API and its revision check; no conflict is fabricated.
  const pattern = `**${decisionsPath}`;
  await second.route(pattern, (route) => route.fulfill({ json: initial }));
  try {
    const url = `/experiments/${id}?candidate=${candidate.id}`;
    for (const tab of [page, second]) {
      await tab.goto(url);
      await expect(
        tab.getByRole("heading", { name: "Evidence", exact: true }),
      ).toBeVisible();
      await tab.getByRole("tab", { name: "Notes", exact: true }).click();
    }
    const noteA = `First tab · ${Date.now()}`;
    const noteB = `Second tab draft · ${Date.now()}`;
    await page.getByRole("textbox", { name: "Notes for NU6102" }).fill(noteA);
    await second.getByRole("textbox", { name: "Notes for NU6102" }).fill(noteB);
    expect((await save(page)).status()).toBe(200);
    expect((await current()).notes).toBe(noteA);
    expect((await save(second)).status()).toBe(409);
    await expect(second.getByRole("alert")).toContainText(
      "This decision changed",
    );
    await expect(
      second.getByRole("textbox", { name: "Notes for NU6102" }),
    ).toHaveValue(noteB);
    expect((await current()).notes).toBe(noteA);
    await second.unroute(pattern);
    // Only this second, explicit Save may replace the first tab's saved note.
    expect((await save(second)).status()).toBe(200);
    expect((await current()).notes).toBe(noteB);
    await second.reload();
    await second.getByRole("tab", { name: "Notes", exact: true }).click();
    await expect(
      second.getByRole("textbox", { name: "Notes for NU6102" }),
    ).toHaveValue(noteB);
  } finally {
    await second.close();
    const latest = await current();
    const restored = await page.request.patch(
      `${decisionsPath}/${candidate.id}`,
      {
        headers: { "If-Match": `"${latest.revision}"` },
        data: {
          pinned: original.pinned,
          notes: original.notes,
          preferred_pose_id: original.preferred_pose_id,
        },
      },
    );
    expect(restored.ok()).toBe(true);
  }
});
