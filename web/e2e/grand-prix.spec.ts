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

  await page.getByRole("tab", { name: "Stratégie" }).click();
  await expect(page.getByRole("heading", { name: "Arrêts" })).toBeVisible();
  await page.getByRole("tab", { name: "Classements" }).click();
  await expect(page.getByText("Après la manche 2").first()).toBeVisible();
});

test("a round the data does not have says so", async ({ page }) => {
  await page.goto("/grand-prix/2025/29");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Course introuvable");
  await expect(page.getByRole("link", { name: /Voir le calendrier/ })).toHaveAttribute("href", "/grand-prix");
});
