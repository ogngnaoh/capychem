import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import type { Study } from "../src/studyModel";

const PARENT = "c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6094";
const EXTENSION = "NS(=O)(=O)c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6102";
const live = process.env.CAPYCHEM_E2E_LIVE === "1";
const launch = live && process.env.CAPYCHEM_E2E_STUDY_LAUNCH === "1";
const fixtureId = process.env.CAPYCHEM_E2E_STUDY;
const matrix = (page: Page) =>
  page.getByRole("region", {
    name: "Candidate evidence across sampling seeds",
  });

async function getStudy(page: Page, id: string): Promise<Study> {
  const response = await page.request.get(`/api/studies/${id}`);
  expect(response.ok()).toBe(true);
  return response.json();
}
async function waitForStudy(page: Page, id: string) {
  await expect
    .poll(async () => (await getStudy(page, id)).status, {
      timeout: 360_000,
      intervals: [1000, 2000, 3000],
    })
    .toMatch(/^(completed|completed_with_errors)$/);
  await page.goto(`/studies/${id}`);
  await expect(matrix(page)).toBeVisible();
  return getStudy(page, id);
}
async function configureTwoRuns(page: Page) {
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByLabel("Embedding attempts per candidate", { exact: true })
    .fill("2");
  await page.getByRole("button", { name: "Remove run 3", exact: true }).click();
}
async function submitStudy(page: Page, doubleClick = false) {
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Review your study" }),
  ).toBeVisible();
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/studies" &&
      r.request().method() === "POST",
  );
  const submit = page.getByRole("button", {
    name: "Run 2 experiments",
    exact: true,
  });
  if (doubleClick) await submit.dblclick({ delay: 10 });
  else await submit.click();
  const result = await response;
  expect(result.ok()).toBe(true);
  const study = (await result.json()) as Study;
  await expect(page).toHaveURL(new RegExp(`/studies/${study.id}$`));
  return { study, request: result.request() };
}

test("live study matrix preserves counts, exact pose links, keyboard views and mobile reading", async ({
  page,
}) => {
  test.skip(
    !live || !fixtureId,
    "Set CAPYCHEM_E2E_LIVE and CAPYCHEM_E2E_STUDY to an existing completed study.",
  );
  const study = await getStudy(page, fixtureId!);
  const candidates = study.candidates!;
  await page.goto(`/studies/${study.id}`);
  const rows = matrix(page).locator("tbody tr");
  await expect(rows).toHaveCount(candidates.length);
  for (const [i, candidate] of candidates.entries()) {
    await expect(rows.nth(i).getByRole("rowheader")).toContainText(
      candidate.name,
    );
    await expect(rows.nth(i).locator(".study-count")).toHaveText([
      `${candidate.review_ready_runs} / ${candidate.planned_runs}`,
      `${candidate.contact_hit_runs} / ${candidate.planned_runs}`,
    ]);
  }
  await page.getByLabel("Filter study candidates").selectOption("contact");
  await expect(rows).toHaveCount(
    candidates.filter((c) => c.contact_hit_runs > 0).length,
  );
  await page.getByLabel("Filter study candidates").selectOption("no_contact");
  await expect(rows).toHaveCount(
    candidates.filter((c) => c.observed_runs > 0 && c.contact_hit_runs === 0)
      .length,
  );
  await page.getByLabel("Filter study candidates").selectOption("all");
  await page
    .getByLabel("Search study candidates")
    .fill("no-such-compound-123456");
  await expect(
    page.getByRole("heading", { name: "No matching candidates" }),
  ).toBeVisible();
  await page.getByLabel("Search study candidates").fill("");
  const candidate = candidates.find((c) =>
    c.observations.some((o) => o.selected_pose_id),
  )!;
  const observation = candidate.observations.find((o) => o.selected_pose_id)!;
  const row = rows.filter({
    has: page.getByRole("rowheader", {
      name: new RegExp(`^${candidate.name} `),
    }),
  });
  const cell = row.getByRole("link").nth(observation.run_ordinal);
  const href = await cell.getAttribute("href");
  expect(href).toContain(`pose=${observation.selected_pose_id}`);
  expect(href).toContain(`attempt=${observation.attempt_id}`);
  await cell.click();
  await expect(page.locator(".molecular-stage canvas")).toHaveAttribute(
    "aria-label",
    expect.stringContaining(observation.selected_pose_id!),
  );
  await page.getByRole("link", { name: "Back to study", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/studies/${study.id}$`));
  const results = page.getByRole("tab", { name: "Results", exact: true });
  await results.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Run details", exact: true }),
  ).toBeFocused();
  await expect(page.getByRole("tabpanel")).toHaveAttribute("id", "study-runs");
  await expect(
    page.getByRole("link", { name: "Open activity", exact: true }),
  ).toHaveCount(study.seed_pairs.length);
  await page.keyboard.press("Home");
  await expect(results).toBeFocused();
  await expect(results).toHaveAttribute("aria-selected", "true");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    await rows
      .first()
      .locator("th strong")
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
  ).toBeGreaterThanOrEqual(13);
  expect(
    await matrix(page).evaluate((el) => el.scrollWidth > el.clientWidth),
  ).toBe(true);
  await matrix(page).evaluate((el) => {
    el.scrollLeft = el.scrollWidth;
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("study setup rejects duplicate seed pairs and recovers a malformed saved draft", async ({
  page,
}) => {
  const posts: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/studies")
      posts.push(r.url());
  });
  await page.goto("/studies/new?mode=demo");
  await expect(
    page.getByRole("heading", { name: "Choose a molecular series" }),
  ).toBeVisible();
  await page
    .getByLabel("Study name", { exact: true })
    .fill("Seed validation draft");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  const firstEmbedding = await page
    .getByLabel("Run 1 embedding seed")
    .inputValue();
  const firstVina = await page.getByLabel("Run 1 vina seed").inputValue();
  await page.getByLabel("Run 2 embedding seed").fill(firstEmbedding);
  await page.getByLabel("Run 2 vina seed").fill(firstVina);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Each embedding and Vina seed pair must be different",
  );
  await expect(
    page.getByRole("heading", {
      name: "Keep the rules fixed. Vary the sampling.",
    }),
  ).toBeVisible();
  await page.evaluate(() =>
    localStorage.setItem(
      "capychem-study-draft-v1-demo",
      JSON.stringify({ config: { name: 17 }, seeds: null, step: 99 }),
    ),
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Choose a molecular series" }),
  ).toBeVisible();
  await expect(page.getByLabel("Study name", { exact: true })).toHaveValue(
    "CDK2 · repeat-seed study",
  );
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Run 3 experiments", exact: true }),
  ).toBeDisabled();
  expect(posts).toEqual([]);
});

test("a supplied study runs end to end once, exports evidence and preserves shortlist provenance", async ({
  page,
}) => {
  test.skip(
    !launch,
    "Requires CAPYCHEM_E2E_STUDY_LAUNCH=1 and an isolated ready science engine.",
  );
  test.setTimeout(600_000);
  const label = `Study UI regression · ${Date.now()}`;
  const posted: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/studies")
      posted.push(r.postData() || "");
  });
  await page.goto("/studies/new");
  await page.getByLabel("Study name", { exact: true }).fill(label);
  await page
    .getByLabel("Candidates", { exact: true })
    .fill(`${PARENT}\n${EXTENSION}`);
  await configureTwoRuns(page);
  const submitted = await submitStudy(page, true);
  expect(posted).toHaveLength(1);
  const replay = await page.request.post("/api/studies", {
    data: submitted.request.postData()!,
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": submitted.request.headers()["idempotency-key"],
    },
  });
  expect(replay.ok()).toBe(true);
  expect((await replay.json()).id).toBe(submitted.study.id);
  const study = await waitForStudy(page, submitted.study.id);
  expect(study.members).toHaveLength(2);
  expect(new Set(study.members.map((m) => m.experiment.id)).size).toBe(2);
  expect(study.candidates).toHaveLength(2);
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export study", exact: true }).click();
  const file = await downloadEvent;
  const artifact = JSON.parse(await readFile((await file.path())!, "utf8"));
  expect(artifact.kind).toBe("repeated_seed_study");
  expect(artifact.study.spec_hash).toBe(study.spec_hash);
  expect(artifact.experiments).toHaveLength(2);
  expect(artifact.study.candidates).toHaveLength(2);
  const observation = study
    .candidates!.find((c) => c.name === "NU6102")!
    .observations.find((o) => o.selected_pose_id)!;
  expect(observation).toBeTruthy();
  await page.goto(
    `/experiments/${observation.experiment_id}?candidate=${observation.candidate_id}&pose=${observation.selected_pose_id}`,
  );
  await page
    .getByRole("button", { name: "Pin to comparison", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Use shortlist in a new round", exact: true })
    .click();
  await expect(
    page.getByRole("radio", { name: /Evaluate candidates/ }),
  ).toBeChecked();
  await expect(page.getByLabel("Candidates", { exact: true })).toHaveValue(
    /NU6102/,
  );
  const roundDraft = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("capychem-setup-draft-v2-live")!),
  );
  expect(roundDraft.config.source).toBe("supplied");
  expect(roundDraft.config.parentId).toBe(observation.experiment_id);
  expect(roundDraft.config.originCandidates[0].origin).toEqual({
    experiment_id: observation.experiment_id,
    candidate_id: observation.candidate_id,
    pose_id: observation.selected_pose_id,
  });
  const roundPosts: string[] = [];
  page.on("request", (r) => {
    if (
      r.method() === "POST" &&
      new URL(r.url()).pathname === "/api/experiments"
    )
      roundPosts.push(r.postData() || "");
  });
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  const roundResponse = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/experiments" &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Run experiment", exact: true })
    .dblclick({ delay: 10 });
  const roundResult = await roundResponse;
  expect(roundResult.ok()).toBe(true);
  const round = await roundResult.json();
  await expect(page).toHaveURL(
    new RegExp(`/experiments/${round.id}/activity$`),
  );
  expect(roundPosts).toHaveLength(1);
  const roundSpec = round.spec?.request ?? round.spec;
  expect(roundSpec.candidate_source.kind).toBe("supplied");
  expect(roundSpec.parent_experiment_id).toBe(observation.experiment_id);
  expect(roundSpec.candidate_origins[0]).toMatchObject({
    experiment_id: observation.experiment_id,
    candidate_id: observation.candidate_id,
    pose_id: observation.selected_pose_id,
  });
  await page.goto(
    `/experiments/${observation.experiment_id}?candidate=${observation.candidate_id}&pose=${observation.selected_pose_id}`,
  );
  await page
    .getByRole("button", {
      name: "Evaluate shortlist across seeds",
      exact: true,
    })
    .click();
  await expect(page.locator(".study-source")).toContainText("Shortlist from");
  await expect(page.getByLabel("Candidates", { exact: true })).toHaveValue(
    /NU6102/,
  );
  await configureTwoRuns(page);
  const derived = await submitStudy(page);
  const saved = await waitForStudy(page, derived.study.id);
  expect(saved.base_spec.candidate_source.kind).toBe("supplied");
  expect(saved.base_spec.candidate_source.candidates).toHaveLength(1);
  expect(saved.base_spec.parent_experiment_id).toBe(observation.experiment_id);
  expect(saved.base_spec.candidate_origins[0]).toMatchObject({
    experiment_id: observation.experiment_id,
    candidate_id: observation.candidate_id,
    pose_id: observation.selected_pose_id,
  });
});

test("mixed study inputs retain invalid, duplicate and excluded outcomes under a stricter profile", async ({
  page,
}) => {
  test.skip(
    !launch,
    "Requires CAPYCHEM_E2E_STUDY_LAUNCH=1 and an isolated ready science engine.",
  );
  test.setTimeout(240_000);
  await page.goto("/studies/new");
  await page
    .getByLabel("Study name", { exact: true })
    .fill(`Mixed study UI regression · ${Date.now()}`);
  await page
    .getByLabel("Candidates", { exact: true })
    .fill(
      `${PARENT}\n${EXTENSION}\n${PARENT.replace("NU6094", "Parent duplicate")}\nC1CC Malformed ring`,
    );
  await configureTwoRuns(page);
  await page
    .getByLabel("Maximum molecular weight", { exact: true })
    .fill("350");
  const { study } = await submitStudy(page);
  const complete = await waitForStudy(page, study.id);
  const expected = {
    NU6094: "Ready · no contact",
    NU6102: "Excluded",
    "Parent duplicate": "Duplicate",
    "Malformed ring": "Invalid input",
  };
  for (const [name, status] of Object.entries(expected)) {
    const candidate = complete.candidates!.find((c) => c.name === name)!;
    const row = matrix(page)
      .locator("tbody tr")
      .filter({
        has: page.getByRole("rowheader", { name: new RegExp(`^${name} `) }),
      });
    await expect(row.getByRole("link")).toHaveCount(2);
    for (const link of await row.getByRole("link").all())
      await expect(link).toContainText(status);
    if (name !== "NU6094") {
      expect(candidate.review_ready_runs).toBe(0);
      expect(candidate.observations.every((o) => !o.selected_pose_id)).toBe(
        true,
      );
    }
  }
  await page.getByLabel("Filter study candidates").selectOption("incomplete");
  await expect(matrix(page).locator("tbody tr")).toHaveCount(3);
});

test("recorded study opens exact evidence and exports with the live API blocked", async ({
  page,
}) => {
  const manifestResponse = await page.request.get(
    "/data/recorded-experiments.json",
  );
  const manifest = await manifestResponse.json();
  test.skip(
    !manifest.studies?.length,
    "The recorded bundle does not include study evidence.",
  );
  const study = manifest.studies[0] as Study;
  const candidate = study.candidates!.find((c) =>
    c.observations.some((o) => o.selected_pose_id),
  )!;
  const observation = candidate.observations.find((o) => o.selected_pose_id)!;
  const apiRequests: string[] = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/"))
      apiRequests.push(r.url());
  });
  await page.route("**/api/**", (r) => r.abort("connectionrefused"));
  await page.goto(`/studies/${study.id}?mode=demo`);
  await expect(matrix(page).locator("tbody tr")).toHaveCount(
    study.candidates!.length,
  );
  const row = matrix(page)
    .locator("tbody tr")
    .filter({
      has: page.getByRole("rowheader", {
        name: new RegExp(`^${candidate.name} `),
      }),
    });
  await row.getByRole("link").nth(observation.run_ordinal).click();
  await expect(page.locator(".molecular-stage canvas")).toHaveAttribute(
    "aria-label",
    expect.stringContaining(observation.selected_pose_id!),
  );
  await expect(page).toHaveURL(/mode=demo/);
  await page.getByRole("link", { name: "Back to study", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/studies/${study.id}\\?mode=demo$`));
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export study", exact: true }).click();
  const download = await event;
  const exported = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(exported.kind).toBe("recorded_study");
  expect(exported.study.id).toBe(study.id);
  expect(exported.experiments).toHaveLength(study.seed_pairs.length);
  // Warning coverage belongs to the preserved polar-series fixture. The first
  // recorded Study is the filmed three-candidate example and has no O–H group.
  const warningStudy = (manifest.studies as Study[]).find((entry) =>
    entry.candidates?.some((c) =>
      c.observations.some((o) =>
        o.hydrogen_preparation?.warnings.some(
          (w) => w.code === "oh_orientation_not_sampled",
        ),
      ),
    ),
  );
  expect(warningStudy).toBeTruthy();
  const flagged = warningStudy!.candidates!.find((c) =>
    c.observations.some((o) =>
      o.hydrogen_preparation?.warnings.some(
        (w) => w.code === "oh_orientation_not_sampled",
      ),
    ),
  );
  expect(flagged).toBeTruthy();
  const flaggedPose = flagged!.observations.find(
    (o) => o.hydrogen_preparation?.warnings.length,
  )!;
  await page.goto(`/studies/${warningStudy!.id}?mode=demo`);
  await matrix(page)
    .locator("tbody tr")
    .filter({
      has: page.getByRole("rowheader", {
        name: new RegExp(`^${flagged!.name} `),
      }),
    })
    .getByRole("link")
    .nth(flaggedPose.run_ordinal)
    .click();
  await expect(page.locator(".evidence-preparation-warning")).toContainText(
    "OH orientation not sampled",
  );
  await page.locator(".pose-calculation-details > summary").click();
  await expect(page.locator(".hydrogen-preparation")).toContainText(
    "sensitivity has not been assessed",
  );
  await expect(page.locator(".hydrogen-preparation")).toContainText(
    "not a measured sensitivity result",
  );
  const older = manifest.experiments.find((r: any) =>
    r.candidates.some(
      (c: any) =>
        c.structureId &&
        r.viewer.structures.some(
          (s: any) => s.id === c.structureId && !s.hydrogenPreparation,
        ),
    ),
  );
  expect(older).toBeTruthy();
  const olderCandidate = older.candidates.find(
    (c: any) =>
      c.structureId &&
      older.viewer.structures.some(
        (s: any) => s.id === c.structureId && !s.hydrogenPreparation,
      ),
  );
  await page.goto(
    `/experiments/${older.experiment.id}?mode=demo&candidate=${olderCandidate.id}&pose=${olderCandidate.structureId}`,
  );
  await expect(
    page.getByRole("heading", { name: "Evidence", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".evidence-preparation-warning")).toHaveCount(0);
  await expect(page.locator(".hydrogen-preparation")).toHaveCount(0);
  expect(apiRequests).toEqual([]);
});
