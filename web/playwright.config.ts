import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { ensureDemo } from "./e2e/demo-seed";

/** Project root; both the API and demo scripts live one level above web/. */
const root = path.resolve(__dirname, "..");

// Generate the demo DB BEFORE Playwright starts any webServer (plugin setup
// runs before globalSetup in Playwright 1.65). The production build is done by
// the `test:e2e` npm script, once, before the runner starts.
const demo = ensureDemo();
process.env.SENTINEL_DEMO_PASSWORD = demo.password;
process.env.SENTINEL_DEMO_USER = demo.username;
process.env.SENTINEL_DEMO_VIEWER = demo.viewer;

const apiCommand =
  `SENTINEL_SESSION_KEY=e2e-session-key-0123456789abcdef ` +
  `SENTINEL_CONFIG="${path.join(root, ".demo-e2e", "settings.toml")}" ` +
  `"${path.join(root, "venv", "bin", "python")}" -m uvicorn api.main:app ` +
  `--host 127.0.0.1 --port 8000`;

export default defineConfig({
  testDir: "./e2e",
  globalSetup: require.resolve("./e2e/global-setup"),
  timeout: 30_000,
  expect: { timeout: 10_000 },
  // All journeys share one seeded demo DB; parallel workers invalidate each other's sessions.
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: apiCommand,
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      cwd: root,
    },
    {
      command: "npm run start",
      url: "http://127.0.0.1:3000/login",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
