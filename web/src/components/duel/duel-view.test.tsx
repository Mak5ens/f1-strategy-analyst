import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Duel } from "@/lib/api/client";
import { DuelChart, DuelSummary, DuelTable } from "./duel-view";

afterEach(cleanup);

const duel = {
  season: 2025,
  first: { code: "LEC", name: "Charles Leclerc", team: "Ferrari", colour: "#e8002d" },
  second: { code: "HAM", name: "Lewis Hamilton", team: "Ferrari", colour: "#e8002d" },
  rounds: [
    {
      round: 6,
      grand_prix: "Grand Prix de Miami",
      qualifying: { part: null, first_s: null, second_s: null, gap_s: null, first_position: 8, second_position: 12 },
      race: {
        first_position: 7,
        second_position: 8,
        first_text: "7",
        second_text: "8",
        first_points: 6,
        second_points: 10,
      },
      pace: { laps: 50, gap_s: -0.077 },
    },
    {
      round: 16,
      grand_prix: "Grand Prix d'Italie",
      qualifying: {
        part: "Q3",
        first_s: 79.007,
        second_s: 79.124,
        gap_s: -0.117,
        first_position: 4,
        second_position: 5,
      },
      race: {
        first_position: 4,
        second_position: 6,
        first_text: "4",
        second_text: "6",
        first_points: 12,
        second_points: 8,
      },
      pace: null,
    },
  ],
  summary: {
    qualifying_first: 2,
    qualifying_second: 0,
    race_first: 2,
    race_second: 0,
    points_first: 18,
    points_second: 18,
    qualifying_gap_s: -0.117,
    pace_gap_s: -0.077,
  },
} as unknown as Duel;

describe("Duel", () => {
  it("sums up the season, a median gap in favour of the faster driver", () => {
    render(<DuelSummary duel={duel} />);
    expect(screen.getByText("-0,117 s")).toBeTruthy();
    expect(screen.getAllByText("en faveur de Charles Leclerc")).toHaveLength(2);
  });

  it("draws a bar for each round with a gap, none where it has none", () => {
    const { container } = render(<DuelChart duel={duel} kind="qualifying" />);
    expect([...container.querySelectorAll("rect[data-round]")].map((bar) => bar.getAttribute("data-round"))).toEqual([
      "16",
    ]);
  });

  it("gives each round its places and gaps, untimed qualifying by its places only, and links the race", () => {
    render(<DuelTable duel={duel} />);
    expect(screen.getByText("· P8 / P12")).toBeTruthy();
    expect(screen.getByText("· Q3 · P4 / P5")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Grand Prix d'Italie" }).getAttribute("href")).toBe(
      "/grand-prix/2025/16?onglet=course&pilotes=LEC,HAM",
    );
  });
});
