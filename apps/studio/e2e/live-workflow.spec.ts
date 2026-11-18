import { expect, test } from "@playwright/test";
import { createRun, waitForRun, NU6102 } from "./live-helpers";
test.skip(
  process.env.CAPYCHEM_E2E_LIVE !== "1",
  "Requires the isolated local API and chemistry worker.",
);
test.setTimeout(150000);

test("lost POST receipt retries the same experiment; exclusions, exact export and fork settings remain traceable", async ({
  page,
}) => {
  const label = `UI durable round · ${Date.now()}`;
  let committedId = "";
  let attempts = 0;
  const keys: string[] = [];
  await page.route("**/api/experiments", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    attempts++;
    keys.push(route.request().headers()["idempotency-key"]);
    if (attempts === 1) {
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      committedId = (await response.json()).id;
      await route.abort("failed");
    } else await route.continue();
  });
  await page.goto("/experiments/new");
  await expect(
    page.getByRole("combobox", { name: "Reference preparation" }),
  ).toBeEnabled();
  await page
    .getByRole("combobox", { name: "Reference preparation" })
    .selectOption("cdk2_1h1s_nu6094_v1");
  await page.getByRole("textbox", { name: "Experiment name" }).fill(label);
  await page
    .getByLabel("Candidates", { exact: true })
    .fill(
      `${NU6102}\n${NU6102.replace(" NU6102", " Duplicate")}\nnot_smiles Broken\nc1ccccc1 WrongScaffold`,
    );
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Embedding attempts per candidate").fill("4");
  await page.getByLabel("Maximum molecular weight").fill("472");
  await page.getByLabel("Maximum rotatable bonds").fill("9");
  await page.getByLabel("Admission time limit").fill("120");
  await page.getByText("Reproducibility settings", { exact: true }).click();
  await page.getByLabel("Embedding seed", { exact: true }).fill("194716");
  await page.getByLabel("Vina seed", { exact: true }).fill("43");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByRole("button", { name: "Run experiment", exact: true })
    .click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /fetch|failed|network/i })
      .first(),
  ).toBeVisible();
  expect(committedId).toBeTruthy();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Review your experiment" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Run experiment", exact: true })
    .dblclick();
  await expect(page).toHaveURL(
    new RegExp(`/experiments/${committedId}/activity`),
  );
  expect(attempts).toBe(2);
  expect(keys[0]).toBe(keys[1]);
  const matches = await (
    await page.request.get(`/api/experiments?q=${encodeURIComponent(label)}`)
  ).json();
  expect(matches.items).toHaveLength(1);
  await waitForRun(page, committedId);
  const rows = (
    await (
      await page.request.get(`/api/experiments/${committedId}/candidates`)
    ).json()
  ).items;
  expect(rows).toHaveLength(4);
  expect(rows.some((c: any) => c.status === "duplicate")).toBe(true);
  expect(rows.some((c: any) => c.status === "invalid")).toBe(true);
  expect(rows.some((c: any) => c.status === "outside_constraints")).toBe(true);
  const candidate = rows.find((c: any) => c.name === "NU6102");
  await page.goto(`/experiments/${committedId}?candidate=${candidate.id}`);
  await expect(page.locator(".molecular-stage canvas")).toBeVisible();
  const sdf = page.getByRole("link", {
    name: "Download selected pose",
    exact: true,
  });
  await expect(sdf).toBeVisible();
  const href = await sdf.getAttribute("href");
  const file = await page.request.get(href!);
  expect(file.ok()).toBe(true);
  expect(await file.text()).toContain("$$$$");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export", exact: true }).click();
  await page.getByRole("button", { name: /Experiment record JSON/ }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain(committedId);
  await page.getByRole("link", { name: "New round", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Experiment name" }),
  ).toHaveValue(`${label} · next round`);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByLabel("Maximum molecular weight")).toHaveValue("472");
  await expect(page.getByLabel("Maximum rotatable bonds")).toHaveValue("9");
  await expect(page.getByLabel("Admission time limit")).toHaveValue("120");
  await page.getByText("Reproducibility settings", { exact: true }).click();
  await expect(page.getByLabel("Embedding seed", { exact: true })).toHaveValue(
    "194716",
  );
  await expect(page.getByLabel("Vina seed", { exact: true })).toHaveValue("43");
  await page.reload();
  await expect(page.getByLabel("Maximum molecular weight")).toHaveValue("472");
});

test("generation runs through the UI and a second generation can be cancelled safely", async ({
  page,
}) => {
  await page.goto("/experiments/new");
  await expect(
    page.getByRole("combobox", { name: "Reference preparation" }),
  ).toBeEnabled();
  await page
    .getByRole("combobox", { name: "Reference preparation" })
    .selectOption("cdk2_1h1s_nu6094_v1");
  await page
    .getByRole("textbox", { name: "Experiment name" })
    .fill(`UI LibInvent · ${Date.now()}`);
  await page.getByRole("radio", { name: /Generate variants/ }).check();
  await page.getByLabel("Raw proposals").fill("4");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Maximum unique candidates").fill("2");
  await page.getByLabel("Embedding attempts per candidate").fill("4");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  let receipt = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/experiments" &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Run experiment", exact: true })
    .click();
  const run = await (await receipt).json();
  await waitForRun(page, run.id);
  const detail = await (
    await page.request.get(`/api/experiments/${run.id}`)
  ).json();
  const source = (detail.spec.request ?? detail.spec).candidate_source;
  expect(source.kind).toBe("libinvent");
  expect(source.raw_proposal_count).toBe(4);
  await expect(page.getByRole("region", { name: "Candidates" })).toBeVisible();
  await page.getByRole("link", { name: "New round", exact: true }).click();
  await page.getByLabel("Raw proposals").fill("128");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  receipt = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/experiments" &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Run experiment", exact: true })
    .click();
  const next = await (await receipt).json();
  await page
    .getByRole("button", { name: "Cancel experiment", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/experiments/${next.id}`)).json())
          .status,
      { timeout: 60000 },
    )
    .toBe("cancelled");
  await expect(
    page.getByRole("heading", { name: "Experiment cancelled" }),
  ).toBeVisible();
});

test("an older directly opened experiment remains live outside the first history page", async ({
  page,
}) => {
  let id = process.env.CAPYCHEM_E2E_EXISTING_EXPERIMENT;
  if (!id) {
    const list = await (
      await page.request.get("/api/experiments?status=completed&limit=1")
    ).json();
    id =
      list.items[0]?.id ??
      (await createRun(page, `Older direct run · ${Date.now()}`)).id;
  }
  let snapshots = 0;
  page.on("request", (r) => {
    if (new URL(r.url()).pathname === `/api/experiments/${id}`) snapshots++;
  });
  // Only the history listing is clipped; the run, chemistry and all snapshots are real.
  await page.route("**/api/experiments", async (route) => {
    if (route.request().method() === "GET")
      await route.fulfill({
        json: { items: [], next_cursor: null, has_more: false },
      });
    else await route.continue();
  });
  await page.goto(`/experiments/${id}`);
  await expect(
    page.getByRole("heading", { name: "Evidence", exact: true }),
  ).toBeVisible();
  const initial = snapshots;
  await expect
    .poll(() => snapshots, { timeout: 12000, intervals: [4500, 1000] })
    .toBeGreaterThan(initial);
  await expect(
    page.getByRole("heading", { name: "Evidence", exact: true }),
  ).toBeVisible();
  const cancelled = await (
    await page.request.get("/api/experiments?status=cancelled&limit=1")
  ).json();
  if (cancelled.items[0]) {
    await page.goto(`/experiments/${cancelled.items[0].id}/activity`);
    await expect(
      page.getByRole("heading", { name: "Experiment cancelled" }),
    ).toBeVisible();
    await expect(page.locator(".calculation-stages li.finished")).toHaveCount(
      0,
    );
  }
});
