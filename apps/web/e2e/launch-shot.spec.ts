import { test } from "@playwright/test";

// Capture harness for the frontend-design critic loop: renders the launch form (/)
// at 1280px and writes a screenshot. The launch page makes no API call on load, so
// no route mock is needed. Output path via SHOT_PATH.

const SHOT_PATH = process.env.SHOT_PATH ?? "/tmp/launch-shot.png";

test("capture / (launch) at 1280px", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByText("Launch an optimization").waitFor({ timeout: 15_000 });
  await page.screenshot({ path: SHOT_PATH, fullPage: true });
});
