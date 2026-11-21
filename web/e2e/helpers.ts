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

export async function login(page: Page, username = credentials().admin) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(credentials().password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("navigation", { name: /main/i })).toBeVisible();
}
