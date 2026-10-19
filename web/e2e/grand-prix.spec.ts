import { expect, test } from "@playwright/test";

// The 2025 Chinese Grand Prix, round 2: in the local lake, or in the synthetic season the CI serves
// (tests/unit/test_grand_prix.py). Only what both share is checked.

test("the calendar leads to a race's page, its tabs and its standings after the round", async ({ page }) => {
  await page.goto("/grand-prix?saison=2025");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Saison 2025");
  await page.getByRole("link", { name: /Chine/ }).click();

  await expect(page).toHaveURL(/\/grand-prix\/2025\/2$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Grand Prix de Chine");
  await expect(page.getByText("Manche 2 · 2025")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Max Verstappen Red Bull Racing" }).first()).toBeVisible();

  await page.getByRole("tab", { name: "Course" }).click();
  const positions = page.getByRole("slider", { name: "Positions" });
  await positions.focus();
  await positions.press("Home");
  await expect(page.getByText("Tour 1", { exact: true })).toBeVisible();
  const drivers = page.getByRole("group", { name: "Pilotes mis en avant" }).getByRole("button");
  await expect(drivers.first()).toHaveAttribute("aria-pressed", "true"); // the winner, highlighted
  // Two drivers highlighted open their duel over the season, whoever they are.
  const pressed = page.getByRole("group", { name: "Pilotes mis en avant" }).locator('button[aria-pressed="true"]');
  while ((await pressed.count()) > 2) await pressed.last().click();
  while ((await pressed.count()) < 2) {
    await page
      .getByRole("group", { name: "Pilotes mis en avant" })
      .locator('button[aria-pressed="false"]')
      .first()
      .click();
  }
  await expect(page.getByRole("link", { name: /sur la saison 2025/ })).toHaveAttribute(
    "href",
    /^\/duel\?saison=2025&a=[A-Z]{3}&b=[A-Z]{3}$/,
  );

  await page.getByRole("tab", { name: "Stratégie" }).click();
  await expect(page.getByRole("heading", { name: "Arrêts" })).toBeVisible();
  // The simulator projects, or says why it cannot (the synthetic race's stints are too short for a line).
  await page.getByRole("tab", { name: "Simulateur" }).click();
  await expect(page.getByText(/Temps de course|ne peut pas être projetée/).first()).toBeVisible();
  await page.getByRole("tab", { name: "Classements" }).click();
  await expect(page.getByText("Après la manche 2").first()).toBeVisible();
});

test("a round the data does not have says so", async ({ page }) => {
  await page.goto("/grand-prix/2025/29");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Course introuvable");
  await expect(page.getByRole("link", { name: /Voir le calendrier/ })).toHaveAttribute("href", "/grand-prix");
});
