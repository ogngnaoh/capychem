import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  workers: 1,
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: process.env.CAPYCHEM_STUDIO_URL || "http://127.0.0.1:5181",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    },
  },
});
