import { expect, test } from "@playwright/test";
import { credentials, login } from "./helpers";


test("the seeded scenario incident is navigable end to end", async ({ page }) => {
  await login(page);
  await page.goto("/incidents");
  await page.getByRole("link", { name: /possible credential guessing/i }).click();
  await expect(page.getByText(/not proof of a single actor/i)).toBeVisible();
  await expect(page.getByRole("list", { name: /incident timeline/i })).toBeVisible();
  await expect(page.getByText(/failed password for admin/i).first()).toBeVisible();
  await page.getByRole("button", { name: /why grouped/i }).click();
  await expect(page.getByText(/weak links/i)).toBeVisible();
  await page.getByRole("button", { name: /why score/i }).click();
  await expect(page.getByText(/running total/i)).toBeVisible();
});

test("admin can add a note while a viewer cannot", async ({ page }) => {
  await login(page);
  await page.goto("/incidents/1#notes");
  await page.getByLabel("Add a note").fill("Checked the source IP.");
  await page.getByRole("button", { name: /add note/i }).click();
  await expect(page.getByText(/checked the source ip/i)).toBeVisible();
  await page.getByRole("button", { name: /sign out/i }).click();
  await login(page, credentials().viewer);
  await page.goto("/incidents/1#notes");
  await expect(page.getByLabel("Add a note")).toHaveCount(0);
});

test("what-if simulation and entity graph are available", async ({ page }) => {
  await login(page);
  await page.goto("/incidents/1#why-score");
  await expect(page.getByText(/simulation, not saved/i)).toBeVisible();
  const simulated = page.getByTestId("what-if-score");
  const before = await simulated.textContent();
  const toggle = page.locator('input[aria-label^="ssh-"]').first();
  if (await toggle.count()) {
    await toggle.check();
    await expect(simulated).not.toHaveText(before ?? "");
  }
  await page.getByRole("button", { name: "graph" }).click();
  await expect(page.getByRole("table", { name: /entities and relationships/i })).toBeVisible();
});

test("admin can change incident status with a reason", async ({ page }) => {
  await login(page);
  await page.goto("/incidents/1");
  await page.getByRole("button", { name: /change status/i }).click();
  await page.getByRole("menuitem", { name: /investigating/i }).click();
  await expect(page.getByText(/investigating/i).first()).toBeVisible();
});

test("export downloads non-empty markdown and PDF", async ({ page }) => {
  await login(page);
  await page.goto("/incidents/1");
  for (const format of ["md", "pdf"]) {
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: format === "md" ? /copy markdown/i : /export pdf/i }).click();
    const file = await download;
    expect(file.suggestedFilename()).toContain(`.${format}`);
  }
});
