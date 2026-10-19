import { describe, expect, it } from "vitest";
import { championship, leaders, median, pace, tone } from "./season";
import { season } from "./season.fixture";

describe("season", () => {
  it("draws the championship of drivers or teams, the first ones highlighted", () => {
    const drivers = championship(season, "drivers");
    expect(drivers.map((line) => [line.code, line.values])).toEqual([
      ["NOR", [25, 44]],
      ["VER", [18, 18]],
    ]);
    expect(championship(season, "teams")[1]?.label).toBe("Red Bull Racing");
    expect(leaders(drivers, 1)).toEqual(["NOR"]);
    expect(pace(season, "race")[0]?.values).toEqual([0, null]);
  });

  it("takes the median of the rounds measured", () => {
    expect(median([0.5, null, 0.4, 0.9])).toEqual({ value: 0.5, count: 3 });
    expect(median([0.2, 0.4])).toEqual({ value: 0.30000000000000004, count: 2 });
    expect(median([null])).toBeNull();
  });

  it("reads a result as a win, a podium, points, none, or out", () => {
    expect([1, 3, 10, 11].map((position) => tone({ position }))).toEqual(["win", "podium", "points", "plain"]);
    expect(tone({ position: null })).toBe("out");
    expect(tone(null)).toBe("none");
  });
});
