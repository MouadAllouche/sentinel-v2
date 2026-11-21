import { expect, test } from "@playwright/test";
import { credentials, login } from "./helpers";


test("creates the user's example rule through the builder", async ({ page }) => {
  await login(page);
  await page.goto("/rules/new");
  await page.getByLabel("Rule id").fill("e2e-failed-logins-by-ip");
  await page.getByLabel("Rule name").fill("E2E failed logins by source IP");
  await page.getByLabel("Event type failed_login").check();
  await page.getByLabel("Tier 1 count").fill("5");
  await page.getByRole("button", { name: /add tier/i }).click();
  await page.getByLabel("Tier 2 count").fill("20");
  await page.getByLabel("Tier 2 severity").selectOption("high");
  await expect(page.getByText(/if ≥ 5 failed logins from the same source ip/i)).toBeVisible();
  await expect(page.getByText(/if ≥ 20 failed logins from the same source ip/i)).toBeVisible();
  await expect(page.getByText(/simulation on historical data/i)).toBeVisible();
  await page.getByRole("button", { name: /save rule/i }).click();
  await page.getByRole("dialog", { name: /review rule changes/i }).getByRole("button", { name: /confirm/i }).click();
  await expect(page).toHaveURL(/\/rules$/);
  await expect(page.getByText(/failed logins grouped by source ip/i).first()).toBeVisible();
});

test("viewer sees a read-only rule view", async ({ page }) => {
  await login(page, credentials().viewer);
  await page.goto("/rules");
  await expect(page.getByText(/view only/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /new rule/i })).toHaveCount(0);
});
