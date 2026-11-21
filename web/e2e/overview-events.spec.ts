import { expect, test } from "@playwright/test";
import { credentials, login } from "./helpers";


test("Overview shows seeded KPIs and a top IP link filters events", async ({ page }) => {
  await login(page);
  await expect(page.getByText(/events \(24 h\)/i)).toBeVisible();
  const ip = page.getByRole("link", { name: /203\.0\.113\.45/ }).first();
  await ip.click();
  await expect(page).toHaveURL(/source_ip=203\.0\.113\.45/);
});

test("Events drawer shows raw JSON and export starts a download", async ({ page }) => {
  await login(page);
  await page.goto("/events");
  await page.getByRole("row").nth(1).click();
  await page.getByRole("button", { name: /show raw data/i }).click();
  await expect(page.getByText(/"event_type"/)).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /export csv/i }).click();
  expect((await download).suggestedFilename()).toMatch(/\.csv$/);
});

test("viewer cannot see admin-only event actions", async ({ page }) => {
  await login(page, credentials().viewer);
  await page.goto("/events");
  await page.getByRole("row").nth(1).click();
  await expect(page.getByRole("button", { name: /add allowlist/i })).toHaveCount(0);
});
