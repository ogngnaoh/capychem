import { expect, test } from "@playwright/test";

test("recorded navigation, direct links, source fork and refresh stay out of the live API", async ({
  page,
}) => {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      apiRequests.push(request.url());
  });
  await page.goto("/?mode=demo");
  await expect(
    page.getByRole("heading", {
      name: "Design and evaluate molecular variants.",
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "View all", exact: true }).click();
  await expect(page).toHaveURL(/\/experiments\?mode=demo/);
  const firstRun = page.locator(".experiment-name-link").first();
  await expect(firstRun).toBeVisible();
  const href = await firstRun.getAttribute("href");
  await firstRun.click();
  await expect(
    page.getByRole("navigation", { name: "Experiment views" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "New round", exact: true }).click();
  await expect(page.getByText(/New round from/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/New round from/)).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Experiment name" }),
  ).toHaveValue(/next round/);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.goto(href!);
  await expect(
    page.getByRole("heading", { name: "Evidence", exact: true }),
  ).toBeVisible();
  expect(apiRequests).toEqual([]);
});

test("a saved draft survives refresh and malformed optional fields recover safely", async ({
  page,
}) => {
  await page.goto("/experiments/new?mode=demo");
  await page
    .getByRole("textbox", { name: "Experiment name" })
    .fill("Persistent design draft");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Set the rules and budget" }),
  ).toBeVisible();
  await page.getByLabel("Maximum calculated logP").fill("3.2");
  await page.reload();
  await expect(page.getByLabel("Maximum calculated logP")).toHaveValue("3.2");
  await expect(
    page.getByRole("heading", { name: "Set the rules and budget" }),
  ).toBeVisible();
  await page.evaluate(() => {
    const key = "capychem-setup-draft-v2-demo";
    const draft = JSON.parse(localStorage.getItem(key)!);
    draft.config.maxCandidates = "bad";
    draft.config.seed = null;
    draft.config.maxLogP = {};
    localStorage.setItem(key, JSON.stringify(draft));
  });
  await page.reload();
  await expect(page.getByLabel("Maximum unique candidates")).toHaveValue("8");
  await expect(page.getByLabel("Maximum calculated logP")).toHaveValue("4.5");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Review your experiment" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Run experiment", exact: true }),
  ).toBeDisabled();
});

test("mobile navigation traps focus, closes on Escape and restores the menu button", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?mode=demo");
  const menu = page.getByRole("button", { name: "Menu", exact: true });
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeHidden();
  await menu.click();
  const dialog = page.getByRole("dialog", { name: "Navigation" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Shift+Tab");
  await expect(
    dialog.getByRole("link", { name: "Help", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(
    dialog.getByRole("button", { name: "Close navigation", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await expect(menu).toBeFocused();
  await menu.click();
  await dialog.getByRole("link", { name: "References", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "CDK2 reference study" }),
  ).toBeVisible();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("search empty states and unknown routes preserve a useful way back", async ({
  page,
}) => {
  await page.goto("/experiments?mode=demo");
  await page
    .getByRole("searchbox", { name: "Search experiments" })
    .fill("no-such-molecule-99999");
  await expect(
    page.getByRole("heading", { name: "No matching experiments" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).last().click();
  await expect(page.locator(".experiment-name-link").first()).toBeVisible();
  await page.goto("/does-not-exist?mode=demo");
  await expect(
    page.getByRole("heading", { name: "Page not found" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Go to overview" }).click();
  await expect(page).toHaveURL(/\/?\?mode=demo/);
  await page.goto("/experiments/not-a-recording?mode=demo");
  await expect(
    page.getByRole("heading", { name: "Experiment not found" }),
  ).toBeVisible();
});

test("reference data failure shows an actionable retry rather than an endless spinner", async ({
  page,
}) => {
  await page.route(
    "**/data/cdk2-references.json",
    (route) => route.fulfill({ status: 503, body: "Unavailable" }),
    { times: 1 },
  );
  await page.goto("/?mode=demo");
  await expect(page.getByRole("alert").first()).toContainText("Unable to load");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator(".overview-molecular-view canvas")).toBeVisible();
});

test("missing experiment and offline API are distinct outcomes", async ({
  page,
}) => {
  await page.route("**/api/experiments/missing**", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Experiment not found." }),
    }),
  );
  await page.goto("/experiments/missing");
  await expect(
    page.getByRole("heading", { name: "Experiment not found" }),
  ).toBeVisible();
  await page.route("**/api/experiments/offline**", (route) =>
    route.abort("connectionrefused"),
  );
  await page.goto("/experiments/offline");
  await expect(
    page.getByRole("heading", {
      name: "Your experiment has not been replaced",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Experiment not found" }),
  ).toHaveCount(0);
});

test("recorded pose, pins and notes persist; exported coordinates follow the selected pose", async ({
  page,
}) => {
  const manifest = await (
    await page.request.get("/data/recorded-experiments.json")
  ).json();
  const record = manifest.experiments.find((r: any) =>
    r.candidates.some((c: any) => c.name === "NU6102"),
  );
  const base = record.candidates.find((c: any) => c.name === "NU6102");
  const root = `/experiments/${record.experiment.id}`;
  await page.goto(`${root}?mode=demo&candidate=${base.id}`);
  const select = page.getByRole("combobox", { name: "Displayed pose" });
  await expect(select).toBeVisible();
  const options = await select
    .locator("option")
    .evaluateAll((nodes) => nodes.map((n) => (n as HTMLOptionElement).value));
  const initial = await select.inputValue();
  const chosen = options.find((p) => p !== initial)!;
  await select.selectOption(chosen);
  await expect(select).toHaveValue(chosen);
  await page
    .getByRole("button", { name: "Pin to comparison", exact: true })
    .click();
  await page.getByRole("tab", { name: "Notes", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Notes for NU6102" })
    .fill("Compare this prepared state with the reference pocket.");
  await page.getByRole("button", { name: "Save note", exact: true }).click();
  await page
    .getByRole("navigation", { name: "Experiment views" })
    .getByRole("link", { name: /^Compare/ })
    .click();
  await expect(
    page
      .getByRole("navigation", { name: "Experiment views" })
      .getByRole("link", { name: /^Compare/ }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    page.getByText("Compare this prepared state with the reference pocket.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Inspect this pose" }).click();
  await page.reload();
  await expect(select).toHaveValue(chosen);
  await expect(
    page.getByRole("button", { name: "Pinned to comparison", exact: true }),
  ).toBeVisible();
  const expected = record.viewer.structures.find((s: any) => s.id === chosen);
  const file = page.getByRole("link", {
    name: "Download selected pose",
    exact: true,
  });
  await expect(file).toHaveAttribute("href", expected.sdfUrl);
  expect(await (await page.request.get(expected.sdfUrl)).text()).toContain(
    "$$$$",
  );
  const png = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Capture molecular view", exact: true })
    .click();
  expect((await png).suggestedFilename()).toMatch(/\.png$/);
  await page.goto(`${root}?mode=demo&candidate=missing`);
  await expect(page.getByRole("alert")).toContainText(
    "This candidate is not in",
  );
  await page.getByRole("button", { name: "Show available candidates" }).click();
  await expect(
    page.getByRole("heading", { name: "Evidence", exact: true }),
  ).toBeVisible();
});

test("help anchors and keyboard skip links preserve the current route and mode", async ({
  page,
}) => {
  await page.goto("/help?mode=demo");
  await page
    .getByRole("link", { name: "Reading the evidence", exact: true })
    .click();
  await expect(page).toHaveURL(/\/help\?mode=demo#evidence$/);
  await page.getByRole("link", { name: "Skip to main content" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/help\?mode=demo#main-content$/);
});

test("mobile history scrolls within its table without shifting the page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/experiments?mode=demo");
  await expect(page.locator(".experiment-name-link").first()).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const table = page.locator(".product-table-wrap");
  expect(await table.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(
    true,
  );
  await table.evaluate((el) => {
    el.scrollLeft = el.scrollWidth;
  });
  await expect(
    page.getByRole("button", { name: "Menu", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("overview study navigation preserves recorded mode and selects the experiment family", async ({
  page,
}) => {
  const apiRequests: string[] = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/"))
      apiRequests.push(r.url());
  });
  await page.goto("/?mode=demo");
  await page.getByRole("tab", { name: "Studies", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toBeVisible();
  await page.getByRole("link", { name: "View all", exact: true }).click();
  await expect(page).toHaveURL(/\/studies\?mode=demo/);
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: "Experiments", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  expect(apiRequests).toEqual([]);
});
