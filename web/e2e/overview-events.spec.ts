import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.SENTINEL_DEMO_PASSWORD ?? "demo-password-123";

async function login(page: Page, username: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("navigation", { name: /main/i })).toBeVisible();
}

test("Overview shows seeded KPIs and a top IP link filters events", async ({ page }) => {
  await login(page, "admin");
  await expect(page.getByText(/events \(24 h\)/i)).toBeVisible();
  const ip = page.getByRole("link", { name: /203\.0\.113\.45/ }).first();
  await ip.click();
  await expect(page).toHaveURL(/source_ip=203\.0\.113\.45/);
});

test("Events drawer shows raw JSON and export starts a download", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/events");
  await page.getByRole("row").nth(1).click();
  await page.getByRole("button", { name: /show raw data/i }).click();
  await expect(page.getByText(/"event_type"/)).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /export csv/i }).click();
  expect((await download).suggestedFilename()).toMatch(/\.csv$/);
});

test("viewer cannot see admin-only event actions", async ({ page }) => {
  await login(page, "viewer");
  await page.goto("/events");
  await page.getByRole("row").nth(1).click();
  await expect(page.getByRole("button", { name: /add allowlist/i })).toHaveCount(0);
});
