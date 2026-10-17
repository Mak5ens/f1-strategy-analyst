import { expect, test } from "@playwright/test";

test("the home page leads to the races, asks for a debrief, and shows the API's version, read through the generated client", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Analyste stratégie F1");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Chaque course");
  await page.getByRole("button", { name: /Monaco 2025/ }).click();
  await expect(page.getByRole("textbox")).toHaveValue("Débrief stratégique du GP de Monaco 2025");
  await expect(page.getByText("API disponible")).toBeVisible();
  await expect(page.getByText(/^· version \d+\.\d+\.\d+$/)).toBeVisible();
});
