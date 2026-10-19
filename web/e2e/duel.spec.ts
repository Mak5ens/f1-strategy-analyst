import { expect, test } from "@playwright/test";

// The latest season, in the local lake or in the synthetic season the CI serves (tests/unit/test_grand_prix.py):
// only what both share is checked.

test("the duel page compares the season's leader to a teammate, and another pair from the form", async ({ page }) => {
  await page.goto("/duel");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("contre");
  await expect(page.getByText("Qualifications").first()).toBeVisible();

  const pilots = page.getByRole("combobox", { name: "Contre" });
  const other = await pilots.locator("option").nth(1).getAttribute("value");
  await pilots.selectOption(other ?? "");
  await page.getByRole("button", { name: "Comparer" }).click();
  await expect(page).toHaveURL(new RegExp(`b=${other}`));
  await expect(page.getByRole("link", { name: /Grand Prix/ }).first()).toHaveAttribute(
    "href",
    /\/grand-prix\/\d{4}\/\d+\?onglet=course&pilotes=/,
  );
});
