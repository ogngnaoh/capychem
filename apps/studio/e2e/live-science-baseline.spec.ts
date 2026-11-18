/** Opt-in real CPU baseline. Every experiment is submitted through the Studio UI. */
import { expect, test, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const enabled = process.env.CAPYCHEM_E2E_LIVE === "1" &&
  process.env.CAPYCHEM_E2E_LIVE_BASELINE === "1";
const output = process.env.CAPYCHEM_E2E_LIVE_BASELINE_DIR;
const resume = process.env.CAPYCHEM_E2E_RESUME_ONLY === "1";
const viewport = { width: 1440, height: 1000 };
const parent = "c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6094";
const extension = "NS(=O)(=O)c1ccc(Nc2nc(OCC3CCCCC3)c3nc[nH]c3n2)cc1 NU6102";
const sha = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");
test.skip(!enabled || !output, "Requires explicit real-science opt-in and an isolated evidence directory.");
test.setTimeout(600_000);
test.use({ viewport, deviceScaleFactor: 1 });

async function save(path: string, value: unknown) {
  await writeFile(path, JSON.stringify(value, null, 2) + "\n");
}

async function verifyDownload(page: Page, id: string, candidate: any, directory: string) {
  const exportedResponse = await page.request.get(`/api/experiments/${id}/export`);
  expect(exportedResponse.ok()).toBe(true);
  const exported = await exportedResponse.json();
  const pose = candidate.poses.find((p: any) => p.id === candidate.structureId);
  expect(pose).toBeTruthy();
  const artifact = exported.artifacts.find((a: any) => a.url === pose.sdfUrl);
  expect(artifact).toBeTruthy();
  const event = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download selected pose", exact: true }).click();
  const download = await event;
  const bytes = await readFile((await download.path())!);
  expect(sha(bytes)).toBe(artifact.sha256);
  expect(bytes.length).toBe(artifact.size_bytes);
  expect(bytes.toString()).toContain("$$$$");
  await writeFile(resolve(directory, "selected-pose.sdf"), bytes);
  const recordEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export", exact: true }).click();
  await page.getByRole("button", { name: /Experiment record/ }).click();
  const recordDownload = await recordEvent;
  const browserExport = JSON.parse(await readFile((await recordDownload.path())!, "utf8"));
  expect(browserExport.experiment.id).toBe(id);
  expect(browserExport.experiment.spec).toEqual(exported.experiment.spec);
  expect(browserExport.artifacts).toEqual(exported.artifacts);
  await save(resolve(directory, "browser-export.json"), browserExport);
  const reportArtifact = exported.artifacts.find((a: any) =>
    a.relative_path === "report.json" && a.attempt_id === exported.experiment.counts.active_attempt_id,
  );
  expect(reportArtifact).toBeTruthy();
  const reportResponse = await page.request.get(`/api${reportArtifact.url}`);
  expect(reportResponse.ok()).toBe(true);
  const reportBytes = await reportResponse.body();
  expect(sha(reportBytes)).toBe(reportArtifact.sha256);
  await writeFile(resolve(directory, "report.json"), reportBytes);
  return {
    experimentId: id,
    candidateId: candidate.id,
    candidateName: candidate.name,
    poseId: candidate.structureId,
    preparedStateId: pose.preparedStateId,
    preparedSmiles: pose.preparedSmiles,
    sdfArtifactId: artifact.id,
    sdfSha256: artifact.sha256,
    sdfBytes: artifact.size_bytes,
    reportSha256: reportArtifact.sha256,
    activeAttemptId: exported.experiment.counts.active_attempt_id,
    requestSpec: exported.experiment.spec,
    counts: exported.experiment.counts,
  };
}

async function runFromUI(page: Page, kind: "supplied" | "libinvent") {
  const directory = resolve(output!, kind);
  await mkdir(directory, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const readyResponse = await page.request.get("/api/experiments/readiness");
  expect(readyResponse.ok()).toBe(true);
  const ready = await readyResponse.json();
  expect(ready.ready).toBe(true);
  if (kind === "libinvent") expect(ready.capabilities.libinvent).toBe(true);
  await save(resolve(directory, "readiness.json"), ready);
  const label = `Live UI baseline · ${kind} · ${Date.now()}`;
  await page.goto("/experiments/new");
  await expect(page.getByRole("combobox", { name: "Reference preparation" })).toBeEnabled();
  await page.getByRole("combobox", { name: "Reference preparation" }).selectOption("cdk2_1h1s_nu6094_v1");
  await page.getByRole("textbox", { name: "Experiment name" }).fill(label);
  if (kind === "supplied") {
    await page.getByRole("radio", { name: /Evaluate candidates/ }).check();
    await page.getByLabel("Candidates", { exact: true }).fill(`${parent}\n${extension}`);
  } else {
    await page.getByRole("radio", { name: /Generate variants/ }).check();
    await page.getByLabel("Raw proposals").fill("12");
    await page.getByLabel("Generation seed").fill("47");
  }
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("Maximum molecular weight").fill("450");
  await page.getByLabel("Maximum calculated logP").fill("4.5");
  await page.getByLabel("Maximum rotatable bonds").fill("8");
  await page.getByLabel("Maximum unique candidates").fill("6");
  await page.getByLabel("Embedding attempts per candidate").fill("16");
  await page.getByLabel("Admission time limit").fill("180");
  await page.getByText("Reproducibility settings", { exact: true }).click();
  await page.getByLabel("Embedding seed").fill("194715");
  await page.getByLabel("Vina seed").fill("42");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review your experiment" })).toBeVisible();
  const responseEvent = page.waitForResponse((r) =>
    new URL(r.url()).pathname === "/api/experiments" && r.request().method() === "POST",
  );
  const started = Date.now();
  await page.getByRole("button", { name: "Run experiment", exact: true }).click();
  const response = await responseEvent;
  expect(response.status()).toBe(201);
  const submitted = await response.json();
  const request = response.request().postDataJSON();
  expect(request.candidate_source.kind).toBe(kind);
  expect(request.seeds).toEqual({ embedding: 194715, vina: 42 });
  await save(resolve(directory, "submission.json"), {
    submitted, request, idempotencyKey: response.request().headers()["idempotency-key"],
    submittedAt: new Date(started).toISOString(),
  });
  console.log(JSON.stringify({ event: "live-ui-submitted", kind, id: submitted.id, directory }));
  await expect(page).toHaveURL(new RegExp(`/experiments/${submitted.id}/activity$`));
  await expect(page.getByRole("heading", { name: /Waiting for the local worker|Calculation in progress|Calculation completed/ })).toBeVisible();
  const observed: any[] = [];
  await expect.poll(async () => {
    const detail = await (await page.request.get(`/api/experiments/${submitted.id}`)).json();
    const last = observed.at(-1);
    if (!last || last.status !== detail.status || last.stage !== detail.stage) {
      observed.push({ elapsedSeconds: (Date.now() - started) / 1000, status: detail.status, stage: detail.stage, counts: detail.counts });
      await save(resolve(directory, "observed-progress.json"), observed);
    }
    return detail.status;
  }, { timeout: 540_000, intervals: [1000, 2000, 3000] }).toMatch(/^(completed|completed_with_errors|failed|cancelled)$/);
  const browserWaitSeconds = (Date.now() - started) / 1000;
  const detail = await (await page.request.get(`/api/experiments/${submitted.id}`)).json();
  await save(resolve(directory, "detail.json"), detail);
  expect(detail.status).toBe("completed");
  await expect(page.getByRole("heading", { name: "Calculation completed", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Inspect candidates", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/experiments/${submitted.id}$`));
  const candidates = (await (await page.request.get(`/api/experiments/${submitted.id}/candidates`)).json()).items;
  await save(resolve(directory, "candidates.json"), candidates);
  expect(candidates).toHaveLength(kind === "supplied" ? 2 : 12);
  const candidate = kind === "supplied"
    ? candidates.find((c: any) => c.name === "NU6102")
    : candidates.find((c: any) => c.reviewReady && c.structureId) ?? candidates.find((c: any) => c.structureId);
  expect(candidate, "The fixed baseline should produce an inspectable pose; review a changed yield").toBeTruthy();
  await page.getByRole("button", { name: candidate.name, exact: true }).click();
  await expect(page.locator(".stage-heading h2")).toHaveText(candidate.name);
  await expect(page.locator(".stage-heading p")).toContainText("Computed pose");
  await expect(page.locator(".molecular-stage canvas")).toHaveAttribute("aria-label", expect.stringContaining(candidate.structureId));
  if (kind === "supplied") {
    expect(candidate.asp86Contact).toBe(true);
    expect(candidate.reviewReady).toBe(true);
    expect(candidates.find((c: any) => c.name === "NU6094").asp86Contact).toBe(false);
    const contact = page.getByRole("button", { name: /^ASP86 / });
    await contact.click();
    await expect(contact).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator(".contact-atom-details")).toContainText("donor–acceptor");
  }
  const verified = await verifyDownload(page, submitted.id, candidate, directory);
  await page.reload();
  await expect(page.locator(".molecular-stage canvas")).toHaveAttribute("aria-label", expect.stringContaining(verified.poseId));
  const events = await (await page.request.get(`/api/experiments/${submitted.id}/events?limit=500`)).json();
  await save(resolve(directory, "events.json"), events);
  expect(errors).toEqual([]);
  const result = { ...verified, kind, status: "pass", browserWaitSeconds, observed, errors, reloadPreservedIdentity: true,
    label, viewport, deviceScaleFactor: 1 };
  await save(resolve(directory, "result.json"), result);
  console.log(JSON.stringify({ event: "live-ui-verified", kind, id: submitted.id, browserWaitSeconds, counts: verified.counts }));
}

test("real supplied CDK2 controls run from setup through evidence and exact export", async ({ page }) => {
  test.skip(resume, "Submission disabled during post-restart verification.");
  await runFromUI(page, "supplied");
});

test("real fixed-seed LibInvent run preserves every proposal through review and export", async ({ page }) => {
  test.skip(resume, "Submission disabled during post-restart verification.");
  await runFromUI(page, "libinvent");
});

test("saved live results retain pose and artifact identity after an operator-controlled restart", async ({ page }) => {
  test.skip(!resume, "Run separately after restarting the owned local stack; submits no jobs.");
  const evidence = [];
  for (const kind of ["supplied", "libinvent"]) {
    const directory = resolve(output!, kind);
    const prior = JSON.parse(await readFile(resolve(directory, "result.json"), "utf8"));
    await page.goto(`/experiments/${prior.experimentId}?candidate=${prior.candidateId}&pose=${prior.poseId}`);
    await expect(page.locator(".molecular-stage canvas")).toHaveAttribute("aria-label", expect.stringContaining(prior.poseId));
    const candidates = (await (await page.request.get(`/api/experiments/${prior.experimentId}/candidates`)).json()).items;
    const candidate = candidates.find((c: any) => c.id === prior.candidateId);
    const destination = resolve(directory, "after-restart");
    await mkdir(destination, { recursive: true });
    const current = await verifyDownload(page, prior.experimentId, candidate, destination);
    for (const key of ["poseId", "preparedStateId", "preparedSmiles", "sdfArtifactId", "sdfSha256", "reportSha256", "activeAttemptId", "requestSpec", "counts"] as const) {
      expect(current[key]).toEqual(prior[key]);
    }
    evidence.push({ kind, status: "pass", ...current });
  }
  await save(resolve(output!, "restart-verification.json"), evidence);
});
