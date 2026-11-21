import { expect, test } from "@playwright/test";
import { credentials, login } from "./helpers";

/** Runs against `npm run start` (production build), not the dev server. */
test("production login hydrates and authenticates", async ({ page }) => {
  const response = await page.goto("/login");
  expect(response?.status()).toBe(200);
  const csp = response?.headers()["content-security-policy"] ?? "";
  const nonce = /'nonce-([^']+)'/.exec(csp)?.[1];
  expect(nonce).toBeTruthy();

  await login(page);
  await expect(page.getByRole("link", { name: /events/i })).toBeVisible();
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(page).toHaveURL(/\/login/);
});

test("viewer cannot sign in as admin-only routes", async ({ page }) => {
  await login(page, credentials().viewer);
  await page.goto("/users");
  await expect(page).toHaveURL(/error=forbidden/);
});
