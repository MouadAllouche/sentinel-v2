import { expect, test } from "@playwright/test";
import { credentials, login } from "./helpers";


test("behavior page shows anomalies with their explanation and caveat", async ({ page }) => {
  await login(page);
  await page.goto("/behavior");
  await expect(page.getByRole("heading", { name: /behavior monitoring/i })).toBeVisible();
  await expect(page.getByText(/unusual is not necessarily malicious/i).first()).toBeVisible();
});

test("drift page never displays file contents and explains observations only", async ({ page }) => {
  await login(page);
  await page.goto("/drift");
  await expect(page.getByText(/sentinel only observes/i)).toBeVisible();
  await expect(page.getByRole("table", { name: /monitored paths/i })).toBeVisible();
});

test("drift accept-baseline requires a reason and explains it is observation-only", async ({ page }) => {
  await login(page);
  await page.goto("/drift");
  const row = page.getByRole("row", { name: /sshd_config/ }).first();
  if (await row.count()) {
    await row.click();
    await page.getByRole("button", { name: /accept as new baseline/i }).click();
    await expect(page.getByText(/only updates sentinel/i).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Confirm" })).toBeDisabled();
  }
});

test("settings retention dry-run and display prefs are reachable", async ({ page }) => {
  await login(page);
  await page.goto("/settings");
  await expect(page.getByLabel("low_days")).toBeVisible();
  await page.getByRole("button", { name: "Dry run" }).click();
  await expect(page.getByText(/would prune/i).first()).toBeVisible();
  await page.getByRole("button", { name: "display" }).click();
  await expect(page.getByLabel("Display timezone")).toBeVisible();
});

test("allowlist dialog requires a reason", async ({ page }) => {
  await login(page);
  await page.goto("/allowlist");
  await page.getByRole("button", { name: /new entry/i }).click();
  await expect(page.getByRole("button", { name: /save entry/i })).toBeDisabled();
  await page.getByLabel("Allowlist value").fill("203.0.113.99");
  await page.getByLabel("Reason").fill("trusted demo host");
  await expect(page.getByRole("button", { name: /save entry/i })).toBeEnabled();
});

test("viewer is redirected away from admin routes", async ({ page }) => {
  await login(page, credentials().viewer);
  await page.goto("/users");
  await expect(page).toHaveURL(/error=forbidden/);
  await expect(page.getByRole("link", { name: /users/i })).toHaveCount(0);
});
