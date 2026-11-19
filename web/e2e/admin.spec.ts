import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.SENTINEL_DEMO_PASSWORD ?? "demo-password-123";

async function login(page: Page, username = "admin") {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("navigation", { name: /main/i })).toBeVisible();
}

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

test("viewer is redirected away from admin routes", async ({ page }) => {
  await login(page, "viewer");
  await page.goto("/users");
  await expect(page).toHaveURL(/error=forbidden/);
  await expect(page.getByRole("link", { name: /users/i })).toHaveCount(0);
});
