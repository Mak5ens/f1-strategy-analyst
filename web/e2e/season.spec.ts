import { expect, test } from "@playwright/test";

// The latest season of the local lake, or the synthetic one the CI serves: only what both share is checked.

test("the season page tells the championship round by round and opens a round's race", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Saison" }).click();
  await expect(page).toHaveURL(/\/saison$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Saison \d{4}$/);

  const chart = page.getByRole("slider", { name: /Championnat/ });
  await chart.focus();
  await chart.press("Home");
  await expect(page.getByRole("status").first()).toContainText("Après la manche");
  await page.getByRole("button", { name: "Équipes" }).click();
  await expect(page.getByRole("slider", { name: "Championnat · Équipes" })).toBeVisible();

  await expect(page.getByRole("heading", { name: "Rythme des équipes" })).toBeVisible();
  await page.getByRole("table").first().getByRole("link").first().click();
  await expect(page).toHaveURL(/\/grand-prix\/\d{4}\/\d+$/);
});
