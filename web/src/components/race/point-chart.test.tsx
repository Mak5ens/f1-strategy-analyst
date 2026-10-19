import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { RaceLaps } from "@/lib/api/client";
import { PointChart } from "./point-chart";

afterEach(cleanup);

const lap = (n: number, position: number, gap_s: number) => ({
  lap: n,
  position,
  gap_s,
  lap_time_s: 90,
  compound: "MEDIUM",
  tyre_age: n,
  pit: null,
});
const driver = (code: string, name: string, laps: ReturnType<typeof lap>[]) => ({
  driver: { code, name, team: code, colour: null },
  grid: 1,
  laps,
  pace: [],
});
const race = {
  season: 2025,
  round: 16,
  total_laps: 50,
  neutralizations: [],
  events: [],
  drivers: [
    driver("VER", "Max Verstappen", [lap(10, 1, 0), lap(11, 1, 0), lap(12, 1, 0)]),
    driver("LEC", "Charles Leclerc", [lap(10, 2, 1), lap(11, 2, 3), lap(12, 2, 4)]),
    driver("PIA", "Oscar Piastri", [lap(10, 3, 2), lap(11, 3, 4), lap(12, 3, 6)]),
  ],
} as unknown as RaceLaps;

describe("PointChart", () => {
  it("draws the analysis' drivers only, zoomed on its laps, gaps to its reference", () => {
    const { container } = render(
      <PointChart
        race={race}
        chart={{ kind: "gaps", drivers: ["LEC", "PIA"], reference: "PIA", from_lap: 10, to_lap: 12 }}
        label="Cycle d'arrêts de Leclerc face à Piastri"
      />,
    );
    expect([...container.querySelectorAll("[data-driver]")].map((g) => g.getAttribute("data-driver"))).toEqual([
      "LEC",
      "PIA",
    ]);
    const slider = screen.getByRole("slider");
    expect([slider.getAttribute("aria-valuemin"), slider.getAttribute("aria-valuemax")]).toEqual(["10", "12"]);
    expect(screen.getByText(/par rapport à Oscar Piastri · tours 10 à 12/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Voir toute la course/ }).getAttribute("href")).toBe(
      "/grand-prix/2025/16?onglet=course&pilotes=LEC,PIA",
    );
  });
});
