import { expect, test, type Page } from "@playwright/test";
import { createRun, waitForRun, NU6102 } from "./live-helpers";
const NU6094 = "c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6094";
const mixedInputs = [
  NU6094,
  NU6102,
  "c1ccc(Nc2nc(OCC3CCCCC3)c3[nH]cnc3n2)cc1 Tautomer duplicate",
  "C1CC Malformed ring",
  "Cn1c(=O)c2c(ncn2C)n(C)c1=O Outside scaffold",
  "Clc1cccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)c1 Outside attachment",
].join("\n");
async function candidates(page: Page, id: string) {
  const response = await page.request.get(`/api/experiments/${id}/candidates`);
  expect(response.ok()).toBe(true);
  return (await response.json()).items as any[];
}
async function showMetrics(page: Page) {
  await page.getByRole("radio", { name: "Metrics table", exact: true }).click();
}

test("live mixed inputs retain distinct outcomes, explicit links and normalization provenance", async ({
  page,
}) => {
  test.skip(
    process.env.CAPYCHEM_E2E_LIVE !== "1",
    "Requires isolated local science engine.",
  );
  test.setTimeout(150000);
  const id =
    process.env.CAPYCHEM_E2E_MIXED_EXPERIMENT ??
    (await createRun(page, `Mixed review · ${Date.now()}`, mixedInputs)).id;
  await waitForRun(page, id);
  const rows = await candidates(page, id);
  const ready = rows.filter((c) => c.reviewReady && c.structureId);
  const table = page.getByRole("region", { name: "Candidates", exact: true });
  const filters = page.getByRole("group", {
    name: "Filter candidate outcomes",
  });
  await expect(page.locator(".stage-heading h2")).toHaveText(ready[0].name);
  await showMetrics(page);
  await filters.getByRole("button", { name: /^Ready to inspect/ }).click();
  await expect(table.locator("tbody tr")).toHaveCount(ready.length);
  await filters.getByRole("button", { name: /^Asp86 \+ ready/ }).click();
  await expect(table.locator("tbody tr")).toHaveCount(
    rows.filter((c) => c.reviewReady && c.asp86Contact).length,
  );
  await filters.getByRole("button", { name: /^Not evaluated/ }).click();
  await expect(table.locator("tbody tr")).toHaveCount(
    rows.filter((c) => !c.structureId).length,
  );
  const duplicate = rows.find((c) => c.status === "duplicate");
  await page.goto(`/experiments/${id}?candidate=${duplicate.id}`);
  await expect(page.locator(".stage-heading h2")).toHaveText(duplicate.name);
  await expect(page.locator(".stage-loading")).toContainText(
    "after preparation and normalization",
  );
  expect(duplicate.duplicateOfSourceId).toBeTruthy();
  const original = rows.find(
    (c) => c.sourceId === duplicate.duplicateOfSourceId,
  );
  await page
    .getByRole("button", {
      name: `Open original · ${original.name}`,
      exact: true,
    })
    .click();
  await expect(page.locator(".stage-heading h2")).toHaveText(original.name);
  await page.reload();
  await expect(page.locator(".stage-heading h2")).toHaveText(original.name);
  const invalid = rows.find((c) => c.status === "invalid");
  await page.goto(`/experiments/${id}?candidate=${invalid.id}`);
  await expect(page.locator(".stage-loading")).toContainText(
    /could not be parsed/,
  );
  const outside = rows.find((c) =>
    c.failures.includes("parent_scaffold_not_retained"),
  );
  await page.goto(`/experiments/${id}?candidate=${outside.id}`);
  await expect(page.locator(".stage-loading")).toContainText(
    "outside this workflow’s scope",
  );
  const attachment = rows.find((c) =>
    c.failures.includes("modification_outside_declared_para_attachment"),
  );
  await page.goto(`/experiments/${id}?candidate=${attachment.id}`);
  await expect(page.locator(".stage-loading")).toContainText(
    "permitted para carbon (C20)",
  );
  await expect(page.locator(".stage-loading")).toContainText(
    "4.71 exceeds the limit of 4.5",
  );
  await page
    .getByRole("button", { name: /^Inspect evaluated candidate/ })
    .click();
  await expect(page.locator(".molecular-stage canvas")).toBeVisible();
});

test("a completed no-hit batch opens a pose and keeps unevaluated molecules distinguishable", async ({
  page,
}) => {
  test.skip(
    process.env.CAPYCHEM_E2E_LIVE !== "1",
    "Requires isolated local science engine.",
  );
  test.setTimeout(150000);
  const id =
    process.env.CAPYCHEM_E2E_NO_HIT_EXPERIMENT ??
    (
      await createRun(
        page,
        `No hit review · ${Date.now()}`,
        `c1ccccc1 Outside scaffold\n${NU6094}`,
      )
    ).id;
  await waitForRun(page, id);
  const rows = await candidates(page, id);
  const first = rows.find((c) => c.reviewReady && c.structureId);
  expect(first).toBeTruthy();
  expect(rows[0].structureId).toBeFalsy();
  await expect(page.locator(".stage-heading h2")).toHaveText(first.name);
  expect(
    await page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("capychem-studio-ui-v2-live")!)
          .selectedId,
    ),
  ).toBeUndefined();
  await page.reload();
  await expect(page.locator(".stage-heading h2")).toHaveText(first.name);
  await expect(page.locator(".molecular-stage canvas")).toBeVisible();
  await expect(page.locator(".workspace-outcomes")).toContainText(
    "No predicted Asp86 contact",
  );
  await showMetrics(page);
  await page
    .getByRole("group", { name: "Filter candidate outcomes" })
    .getByRole("button", { name: /^Asp86 \+ ready/ })
    .click();
  await expect(
    page.getByText("No compounds match", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Show all inputs", exact: true })
    .click();
  await expect(page.locator(".candidate-panel tbody tr")).toHaveCount(
    rows.length,
  );
  await page.goto(`/experiments/${id}?candidate=${rows[0].id}`);
  await expect(page.locator(".stage-heading h2")).toHaveText(rows[0].name);
  await expect(page.locator(".stage-loading")).toContainText(
    "Excluded before evaluation",
  );
  await page.reload();
  await expect(page.locator(".stage-heading h2")).toHaveText(rows[0].name);
});

test("recorded comparison has an explicit baseline, neutral property deltas and exact preferred-pose identity", async ({
  page,
}) => {
  const manifest = await (
    await page.request.get("/data/recorded-experiments.json")
  ).json();
  const record = manifest.experiments.find((r: any) =>
    r.candidates.some((c: any) => c.name === "NU6102"),
  );
  const parent = record.candidates.find((c: any) => c.name === "NU6094");
  const candidate = record.candidates.find((c: any) => c.name === "NU6102");
  const root = `/experiments/${record.experiment.id}`;
  const apiRequests: string[] = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/"))
      apiRequests.push(r.url());
  });
  for (const c of [parent, candidate]) {
    await page.goto(`${root}?mode=demo&candidate=${c.id}`);
    await page
      .getByRole("button", { name: "Pin to comparison", exact: true })
      .click();
  }
  await page
    .getByRole("navigation", { name: "Experiment views" })
    .getByRole("link", { name: /^Compare/ })
    .click();
  await expect(
    page
      .getByRole("navigation", { name: "Experiment views" })
      .getByRole("link", { name: /^Compare/ }),
  ).toHaveAttribute("aria-current", "page");
  await page
    .getByLabel("Comparison baseline", { exact: true })
    .selectOption(parent.id);
  await expect(page.getByLabel("Compare with", { exact: true })).toHaveValue(
    candidate.id,
  );
  const card = page.locator(".comparison-candidate").filter({
    has: page.getByRole("heading", { name: "NU6102", exact: true }),
  });
  await expect(card.locator(".comparison-identity")).toContainText(
    /Pose \d+ · state/,
  );
  await expect(card.locator(".comparison-identity")).toContainText(
    "Ready to inspect",
  );
  await expect(card.locator(".property-delta")).toHaveText([
    "+79.08 g/mol",
    "-1.35",
    "+1",
  ]);
  await page
    .getByLabel("Comparison baseline", { exact: true })
    .selectOption(candidate.id);
  const other = page.locator(".comparison-candidate").filter({
    has: page.getByRole("heading", { name: "NU6094", exact: true }),
  });
  await expect(other.locator(".property-delta")).toHaveText([
    "-79.08 g/mol",
    "+1.35",
    "-1",
  ]);
  await card
    .getByText("Exact pose and prepared state", { exact: true })
    .click();
  await expect(card).toContainText(candidate.structureId);
  await card
    .getByRole("link", { name: "Inspect this pose", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`pose=${candidate.structureId}`));
  await page
    .getByRole("navigation", { name: "Experiment views" })
    .getByRole("link", { name: /^Compare/ })
    .click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(
    page.getByLabel("Comparison baseline", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(apiRequests).toEqual([]);
});

test("live known-positive results expose the contact objective separately from geometry and exact pose selection", async ({
  page,
}) => {
  test.skip(
    process.env.CAPYCHEM_E2E_LIVE !== "1",
    "Requires isolated local science engine.",
  );
  test.setTimeout(150000);
  const id =
    process.env.CAPYCHEM_E2E_KNOWN_EXPERIMENT ??
    (
      await createRun(
        page,
        `Known review · ${Date.now()}`,
        `${NU6094}\n${NU6102}`,
      )
    ).id;
  await waitForRun(page, id);
  const rows = await candidates(page, id);
  const hit = rows.find((c) => c.reviewReady && c.asp86Contact);
  expect(hit).toBeTruthy();
  await showMetrics(page);
  await page
    .getByRole("group", { name: "Filter candidate outcomes" })
    .getByRole("button", { name: /^Asp86 \+ ready/ })
    .click();
  await expect(page.locator(".candidate-panel tbody tr")).toHaveCount(
    rows.filter((c) => c.reviewReady && c.asp86Contact).length,
  );
  const row = page
    .locator(".candidate-panel tbody tr")
    .filter({ has: page.getByRole("button", { name: hit.name, exact: true }) });
  await expect(row).toContainText("Detected · eligible");
  await expect(row).toContainText("Ready");
  await row.getByRole("button", { name: hit.name, exact: true }).click();
  await expect(page.locator(".pose-outcome")).toContainText(
    "Asp86 contact detected",
  );
  const alternative = hit.poses.find(
    (p: any) => p.structureId !== hit.structureId,
  );
  if (alternative) {
    await page.goto(
      `/experiments/${id}?candidate=${hit.id}&pose=${alternative.structureId}`,
    );
    await expect(
      page.getByLabel("Displayed pose", { exact: true }),
    ).toHaveValue(alternative.structureId);
    await page.reload();
    await expect(
      page.getByLabel("Displayed pose", { exact: true }),
    ).toHaveValue(alternative.structureId);
  }
});

test("a strict property limit explains untested molecules without implying binding failure", async ({
  page,
}) => {
  test.skip(
    process.env.CAPYCHEM_E2E_LIVE !== "1",
    "Requires isolated local science engine.",
  );
  test.setTimeout(150000);
  const id =
    process.env.CAPYCHEM_E2E_STRICT_EXPERIMENT ??
    (
      await createRun(
        page,
        `Strict review · ${Date.now()}`,
        `${NU6094}\n${NU6102}`,
        { maxMolecularWeight: 350 },
      )
    ).id;
  await waitForRun(page, id);
  const rows = await candidates(page, id);
  const excluded = rows.find((c) => c.name === "NU6102");
  expect(excluded.structureId).toBeFalsy();
  expect(
    excluded.failures.some((f: string) =>
      /^molecular_weight>350(?:\.0)?$/.test(f),
    ),
  ).toBe(true);
  await expect(page.locator(".workspace-outcomes")).toContainText(
    "1 ready to inspect",
  );
  await expect(page.locator(".workspace-outcomes")).toContainText(
    "No predicted Asp86 contact",
  );
  await page.goto(`/experiments/${id}?candidate=${excluded.id}`);
  await expect(page.locator(".stage-loading")).toContainText(
    "Molecular weight",
  );
  await expect(page.locator(".stage-loading")).toContainText(
    "exceeds the limit of 350 g/mol",
  );
  await expect(page.locator(".pose-outcome")).toContainText(
    "Contact not assessed",
  );
  await showMetrics(page);
  await page
    .getByRole("group", { name: "Filter candidate outcomes" })
    .getByRole("button", { name: /^Not evaluated/ })
    .click();
  await expect(page.locator(".candidate-panel tbody tr")).toHaveCount(1);
  await expect(page.locator(".candidate-panel tbody tr")).toContainText(
    "Not assessed",
  );
  await page.getByRole("link", { name: "New round", exact: true }).click();
  await expect(page.locator(".fork-context")).toContainText(
    "Copies its settings and inputs",
  );
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByLabel("Maximum molecular weight")).toHaveValue("350");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.locator(".review-input-preview")).toContainText("NU6094");
  await expect(page.locator(".review-input-preview")).toContainText("NU6102");
  await page
    .getByRole("button", { name: "Edit candidates", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Choose your candidates" }),
  ).toBeVisible();
});

test("real alternative poses update table evidence and filters without treating a rejected contact as an objective hit", async ({
  page,
}) => {
  const manifest = await (
    await page.request.get("/data/recorded-experiments.json")
  ).json();
  const record = manifest.experiments.find((r: any) =>
    r.candidates.some(
      (c: any) =>
        c.asp86Contact &&
        c.poses.some((p: any) => p.reviewReady && !p.asp86Contact),
    ),
  );
  expect(record).toBeTruthy();
  const candidate = record.candidates.find(
    (c: any) =>
      c.asp86Contact &&
      c.poses.some((p: any) => p.reviewReady && !p.asp86Contact),
  );
  const alternative = candidate.poses.find(
    (p: any) => p.reviewReady && !p.asp86Contact,
  );
  const root = `/experiments/${record.experiment.id}`;
  await page.goto(`${root}?mode=demo&candidate=${candidate.id}`);
  await page
    .getByLabel("Displayed pose", { exact: true })
    .selectOption(alternative.structureId);
  await showMetrics(page);
  const table = page.getByRole("region", { name: "Candidates", exact: true });
  const row = table.locator("tbody tr").filter({
    has: page.getByRole("button", { name: candidate.name, exact: true }),
  });
  await expect(row).toContainText("Not detected");
  await expect(page.locator(".pose-outcome")).toContainText(
    "No Asp86 H-bond detected",
  );
  await page
    .getByRole("group", { name: "Filter candidate outcomes" })
    .getByRole("button", { name: /^Asp86 \+ ready/ })
    .click();
  await expect(row).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel("Displayed pose", { exact: true })).toHaveValue(
    alternative.structureId,
  );
  await showMetrics(page);
  await expect(row).toContainText("Not detected");
  // The authentic rejected-contact pose may belong to a different experiment
  // than the reviewable non-contact alternative selected above.
  const rejectedRecord = manifest.experiments.find((r: any) =>
    r.candidates.some((c: any) =>
      c.poses.some((p: any) => p.asp86Contact && !p.reviewReady),
    ),
  );
  expect(rejectedRecord).toBeTruthy();
  const rejected = rejectedRecord.candidates.find((c: any) =>
    c.poses.some((p: any) => p.asp86Contact && !p.reviewReady),
  );
  expect(rejected).toBeTruthy();
  const rejectedPose = rejected.poses.find(
    (p: any) => p.asp86Contact && !p.reviewReady,
  );
  await page.goto(
    `/experiments/${rejectedRecord.experiment.id}?mode=demo&candidate=${rejected.id}&pose=${rejectedPose.structureId}`,
  );
  await showMetrics(page);
  const rejectedRow = table.locator("tbody tr").filter({
    has: page.getByRole("button", { name: rejected.name, exact: true }),
  });
  await expect(rejectedRow).toContainText("Detected · outside brief");
  await expect(rejectedRow).toContainText("Outside brief");
  await page
    .getByRole("group", { name: "Filter candidate outcomes" })
    .getByRole("button", { name: /^Outside brief/ })
    .click();
  await expect(rejectedRow).toBeVisible();
  await page
    .getByRole("group", { name: "Filter candidate outcomes" })
    .getByRole("button", { name: /^Asp86 \+ ready/ })
    .click();
  await expect(rejectedRow).toHaveCount(0);
});

test("recorded candidate browsing retains query and sort across list and metrics without remounting the molecular canvas", async ({
  page,
}) => {
  const manifest = await (
    await page.request.get("/data/recorded-experiments.json")
  ).json();
  const record = manifest.experiments.find((r: any) =>
    r.candidates.some((c: any) => c.name === "NU6102"),
  );
  const candidate = record.candidates.find((c: any) => c.name === "NU6102");
  const requests: string[] = [];
  const errors: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      requests.push(request.url());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/**", (route) => route.abort());
  await page.goto(
    `/experiments/${record.experiment.id}?mode=demo&candidate=${candidate.id}`,
  );
  await expect(page).toHaveTitle(/CapyChem/);
  const canvas = page.locator(".molecular-stage canvas");
  await expect(canvas).toBeVisible();
  await canvas.evaluate((element) =>
    element.setAttribute("data-qa-continuity", "original"),
  );
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  await page.keyboard.press("/");
  const search = page.getByRole("searchbox", {
    name: "Filter compounds",
    exact: true,
  });
  await expect(search).toBeFocused();
  await search.fill(candidate.name);
  await expect(page.locator(".candidate-object-list > li")).toHaveCount(1);
  await page.locator(".candidate-list-controls > summary").click();
  await page
    .getByRole("combobox", { name: "Sort candidates", exact: true })
    .click();
  await page.getByRole("option", { name: "Name · Z–A", exact: true }).click();
  await showMetrics(page);
  await expect(search).toHaveValue(candidate.name);
  await expect(page.locator(".candidate-panel tbody tr")).toHaveCount(1);
  await expect(
    page.getByRole("columnheader", { name: "Compound", exact: true }),
  ).toHaveAttribute("aria-sort", "descending");
  await page
    .getByRole("radio", { name: "Candidate list", exact: true })
    .click();
  await expect(canvas).toBeVisible();
  await expect(canvas).toHaveAttribute("data-qa-continuity", "original");
  await expect(search).toHaveValue(candidate.name);
  await expect(
    page.getByRole("combobox", { name: "Sort candidates", exact: true }),
  ).toContainText("Name · Z–A");
  await page
    .getByRole("combobox", { name: "Filter candidate outcomes", exact: true })
    .click();
  await page.getByRole("option", { name: /^Asp86 \+ ready/ }).click();
  const matchingCount = candidate.reviewReady && candidate.asp86Contact ? 1 : 0;
  await expect(page.locator(".candidate-object-list > li")).toHaveCount(
    matchingCount,
  );
  await showMetrics(page);
  await expect(page.locator(".candidate-panel tbody tr")).toHaveCount(
    matchingCount,
  );
  await expect(
    page.getByRole("button", { name: /^Asp86 \+ ready/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("radio", { name: "Candidate list", exact: true })
    .click();
  await expect(canvas).toHaveAttribute("data-qa-continuity", "original");
  await page.getByRole("tab", { name: "Pose", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Properties", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Notes", exact: true }),
  ).toBeFocused();
  await expect(
    page.getByRole("textbox", {
      name: `Notes for ${candidate.name}`,
      exact: true,
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page
    .getByRole("navigation", { name: "Workspace sections" })
    .getByRole("link", { name: "Molecular view", exact: true })
    .click();
  const mobileUrl = new URL(page.url());
  expect(mobileUrl.pathname).toBe(`/experiments/${record.experiment.id}`);
  expect(mobileUrl.searchParams.get("mode")).toBe("demo");
  expect(mobileUrl.searchParams.get("candidate")).toBe(candidate.id);
  expect(mobileUrl.hash).toBe("#workspace-molecule");
  await expect(canvas).toBeInViewport();
  await expect(canvas).toHaveAttribute("data-qa-continuity", "original");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(requests).toEqual([]);
  expect(errors).toEqual([]);
});
