import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests of the built front against a running API (API_URL, http://localhost:8000 by default): `just
 * web-test` builds the front and serves it; the CI starts the API first. WEB_URL tests a front already running
 * instead, e.g. the one of `just up`.
 */
const port = Number(process.env.WEB_E2E_PORT ?? 3002);
const external = process.env.WEB_URL;

export default defineConfig({
  testDir: "e2e",
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: { baseURL: external ?? `http://localhost:${port}`, locale: "fr-FR", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: external
    ? undefined
    : { command: `pnpm build && PORT=${port} pnpm start`, url: `http://localhost:${port}`, timeout: 180_000 },
});
