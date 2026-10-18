import { expect, test } from "@playwright/test";

// The whole human-in-the-loop path, through the real agent and models: a few cents and two minutes a run, so only
// when E2E_AGENT=1 (the CI has no gateway). `E2E_AGENT=1 just web-test` against `just up` and the gateway.
test.skip(!process.env.E2E_AGENT, "needs the agent, the gateway and the race data: set E2E_AGENT=1");
test.setTimeout(300_000);

test("a race, a request, its plan, a review point by point, the debrief published, then questions on it", async ({
  page,
}) => {
  // From the home page, a race is two clicks away: its season, then the race.
  await page.goto("/");
  await page.getByRole("link", { name: "2025", exact: true }).click();
  await expect(page).toHaveURL(/saison=2025/);
  await page
    .locator("#calendrier")
    .getByRole("link", { name: /Italie/ })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Grand Prix d'Italie");

  await page.goto("/");
  await page.getByRole("textbox").fill("Débrief stratégique du GP d'Italie 2025 pour Ferrari");
  await page.getByRole("button", { name: "Demander" }).click(); // routed to the agent: a debrief is asked for
  await expect(page.getByRole("heading", { name: "Plan à valider" })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("group", { name: "Charles Leclerc" })).toBeVisible();

  await page.getByRole("button", { name: /^Lancer \d+ analyses?$/ }).click();
  await expect(page.getByRole("heading", { name: "Revue point par point" })).toBeVisible({ timeout: 180_000 });
  const publish = page.getByRole("button", { name: "Publier le débrief" });
  await expect(publish).toBeDisabled();

  // The first point corrected, with a reason; the others approved in one click.
  const first = page
    .getByRole("listitem")
    .filter({ has: page.getByRole("group") })
    .first();
  await first.getByText("Corriger").click();
  await first.getByRole("textbox").fill("Point corrigé par le test de bout en bout.");
  await expect(publish).toBeDisabled(); // a correction needs its reason
  await first.getByRole("combobox").selectOption("wording");
  await page.getByRole("button", { name: "Tout approuver" }).click();
  await publish.click();

  await expect(page.getByText("Publié", { exact: true })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Point corrigé par le test de bout en bout.")).toBeVisible();
  // A question under the published debrief, then one on another race, refused.
  const question = page.getByRole("textbox", { name: "Questions sur ce débrief" });
  await question.fill("Détaille le cycle d'arrêts de Leclerc face à Russell");
  await page.getByRole("button", { name: "Demander" }).click();
  await expect(page.locator("#questions li").first()).toBeVisible({ timeout: 120_000 });
  await question.fill("Et au Grand Prix de Monaco ?");
  await page.getByRole("button", { name: "Demander" }).click();
  await expect(page.getByText("Question hors de ce débrief.")).toBeVisible({ timeout: 60_000 });

  await page.getByRole("link", { name: /Journal des décisions/ }).click();
  await expect(page.getByText("Corrigé · Formulation")).toBeVisible();
});
