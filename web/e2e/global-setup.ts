import { ensureDemo } from "./demo-seed";

/**
 * Confirm the demo DB exists and re-export credentials to workers. The actual
 * generation happens in playwright.config.ts (before webServers start), because
 * the API must be pointed at the demo DB from its first boot. The demo script is
 * sandboxed: it writes only to `.demo-e2e/` and reads no real system files.
 */
async function globalSetup() {
  const credentials = ensureDemo();
  process.env.SENTINEL_DEMO_PASSWORD = credentials.password;
  process.env.SENTINEL_DEMO_USER = credentials.username;
  process.env.SENTINEL_DEMO_VIEWER = credentials.viewer;
}

export default globalSetup;
