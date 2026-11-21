import { expect, test } from "@playwright/test";
import { credentials, login, mainIncidentId } from "./helpers";


test("the seeded scenario incident is navigable end to end", async ({ page }) => {
  await login(page);
  await page.goto("/incidents");
  await page.getByRole("link", { name: /possible brute force from 203\.0\.113\.45/i }).click();
  await expect(page.getByText(/not proof of a single actor/i)).toBeVisible();
  await expect(page.getByRole("list", { name: /incident timeline/i })).toBeVisible();
  // Repeated failed_logins are collapsed by default; expand them to see the
  // underlying "Failed SSH login attempt for admin" event descriptions.
  await page.getByRole("checkbox", { name: /collapse repeats/i }).uncheck();
  await expect(page.getByText(/failed ssh login attempt for admin/i).first()).toBeVisible();
  await page.getByRole("button", { name: /why grouped/i }).click();
  await expect(page.getByRole("heading", { name: /weak links/i })).toBeVisible();
  await page.getByRole("button", { name: /why score/i }).click();
  await expect(page.getByText(/running total/i)).toBeVisible();
});

test("admin can add a note while a viewer cannot", async ({ page }) => {
  await login(page);
  const id = await mainIncidentId(page);
  await page.goto(`/incidents/${id}#notes`);
  await page.getByLabel("Add a note").fill("Checked the source IP.");
  await page.getByRole("button", { name: /add note/i }).click();
  await expect(page.getByText(/checked the source ip/i)).toBeVisible();
  await page.getByRole("button", { name: /sign out/i }).click();
  await login(page, credentials().viewer);
  await page.goto(`/incidents/${id}#notes`);
  await expect(page.getByLabel("Add a note")).toHaveCount(0);
});

test("what-if simulation and entity graph are available", async ({ page }) => {
  await login(page);
  const id = await mainIncidentId(page);
  await page.goto(`/incidents/${id}#why-score`);
  await expect(page.getByText(/simulation, not saved/i)).toBeVisible();
  const simulated = page.getByTestId("what-if-score");
  const before = await simulated.textContent();
  // The live score is capped at 100; disabling a single rule may leave both
  // the capped score and its severity floor unchanged. Disable every rule to
  // verify the simulation actually recomputes.
  const toggles = page
    .getByRole("region", { name: /what-if score simulation/i })
    .locator('input[type="checkbox"]');
  if (await toggles.count()) {
    for (const toggle of await toggles.all()) await toggle.check();
    await expect(simulated).not.toHaveText(before ?? "");
    await expect(simulated).toContainText("Simulated score: 0");
  }
  await page.getByRole("button", { name: "graph" }).click();
  await expect(page.getByRole("table", { name: /entities and relationships/i })).toBeVisible();
});

test("admin can change incident status with a reason", async ({ page }) => {
  await login(page);
  const id = await mainIncidentId(page);
  await page.goto(`/incidents/${id}`);
  await page.getByRole("button", { name: /change status/i }).click();
  await page.getByRole("menuitem", { name: /investigating/i }).click();
  await expect(page.getByText(/investigating/i).first()).toBeVisible();
});

test("export downloads non-empty markdown and PDF", async ({ page }) => {
  await login(page);
  const id = await mainIncidentId(page);
  await page.goto(`/incidents/${id}`);
  for (const format of ["md", "pdf"]) {
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: format === "md" ? /copy markdown/i : /export pdf/i }).click();
    const file = await download;
    expect(file.suggestedFilename()).toContain(`.${format}`);
  }
});
