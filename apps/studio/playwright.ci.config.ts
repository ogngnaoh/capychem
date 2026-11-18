import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

const port = Number(process.env.CAPYCHEM_STUDIO_CI_PORT || "5189");
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("CAPYCHEM_STUDIO_CI_PORT must be a port between 1 and 65535");
}
if (process.env.CAPYCHEM_E2E_LIVE === "1") {
  throw new Error("Use playwright.config.ts against a running API for live inference tests");
}

const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig(base, {
  forbidOnly: Boolean(process.env.CI),
  use: { baseURL },
  // Serve the build CI just produced; never attach to an operator's dev server.
  webServer: {
    command: `pnpm preview --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
