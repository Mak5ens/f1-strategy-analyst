import { expect, test } from "@playwright/test";

test("the home page shows the API's version, read through the generated client", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Analyste stratégie F1");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByText("Disponible")).toBeVisible();
  await expect(page.getByText(/^Version \d+\.\d+\.\d+$/)).toBeVisible();
});
