import { expect, test } from "@playwright/test";

// The free question of the home page (LAB-206), through the real retrieval pipeline: a few cents a run, so only when
// E2E_AGENT=1 (the CI has no gateway nor index). `E2E_AGENT=1 just web-test` against `just up` and the gateway.
test.skip(!process.env.E2E_AGENT, "needs the API, the FIA index and the gateway: set E2E_AGENT=1");
test.setTimeout(240_000);

test("a rule question is answered on the home page with its FIA sources, and kept among the recent ones", async ({
  page,
}) => {
  const question = "Que risque une équipe en cas de libération dangereuse d'une voiture au stand en 2025 ?";
  await page.goto("/");
  await page.getByRole("textbox").fill(question);
  await page.getByRole("button", { name: "Demander" }).click();

  const answer = page.locator("#reponse");
  await expect(answer.getByText("Réponse du règlement FIA")).toBeVisible({ timeout: 120_000 });
  await expect(page).toHaveURL(/\?question=\d+/);
  await expect(answer.getByText("Sources")).toBeVisible();
  await expect(answer.locator("summary").first()).toContainText(/^S1 · /);
  await expect(answer.getByText("Réponse calculée sur les données")).toHaveCount(0); // never through the agent
  await expect(
    page.getByRole("link", { name: new RegExp(`^Règlement.*${question.slice(0, 30)}`) }).first(),
  ).toBeVisible();
});

test("a question on both the rules and a race's data asks the analyst which path to take", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("textbox").fill("Leclerc avait-il le droit de s'arrêter au tour 20 à Monza 2025 ?");
  await page.getByRole("button", { name: "Demander" }).click();

  const answer = page.locator("#reponse");
  await expect(answer.getByText("À préciser")).toBeVisible({ timeout: 30_000 });
  await answer.getByRole("button", { name: "Le règlement" }).click();
  await expect(answer.getByText("Réponse du règlement FIA")).toBeVisible({ timeout: 120_000 });
});
