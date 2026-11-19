import { expect, test } from "@playwright/test";

test("unauthenticated users are redirected to login", async ({ page }) => {
  await page.goto("/events");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});

test("login renders the shell and logout returns to login", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("a-long-test-password");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("navigation", { name: /main/i })).toBeVisible();
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(page).toHaveURL(/\/login/);
});

test("theme toggle persists", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /theme/i }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: /theme/i })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
