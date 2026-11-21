import { expect, type Page } from "@playwright/test";

/** Credentials come from globalSetup, which reads the demo's mode-0600 file. */
export function credentials() {
  const password = process.env.SENTINEL_DEMO_PASSWORD;
  if (!password) throw new Error("SENTINEL_DEMO_PASSWORD is not set (e2e globalSetup must run)");
  return {
    admin: process.env.SENTINEL_DEMO_USER ?? "demo-admin",
    viewer: process.env.SENTINEL_DEMO_VIEWER ?? "demo-viewer",
    password,
  };
}

/**
 * The baseline cycle emits its own anomaly incident, so the main brute-force
 * incident is not always id 1. Discover it by its seeded title instead of
 * hard-coding an id that depends on event-hash ordering.
 */
export async function mainIncidentId(page: Page): Promise<number> {
  await page.goto("/incidents");
  const href = await page
    .getByRole("link", { name: /possible brute force from 203\.0\.113\.45/i })
    .first()
    .getAttribute("href");
  if (!href) throw new Error("seeded brute-force incident link not found");
  const id = Number(new URL(href, page.url()).pathname.split("/").pop());
  if (!Number.isFinite(id)) throw new Error(`unexpected incident href: ${href}`);
  return id;
}

export async function login(page: Page, username = credentials().admin) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(credentials().password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("navigation", { name: /main/i })).toBeVisible();
}
