import { describe, expect, it } from "vitest";
import type { RaceLaps } from "@/lib/api/client";
import {
  dashed,
  defaultHighlight,
  gapDomain,
  gaps,
  lastLap,
  path,
  positions,
  scale,
  spread,
  ticks,
} from "./race-chart";

const driver = (code: string, team: string, grid: number, laps: [number, number | null, number | null][]) => ({
  driver: { code, name: code, team, colour: null },
  grid,
  laps: laps.map(([lap, position, gap_s]) => ({
    lap,
    position,
    gap_s,
    lap_time_s: null,
    compound: null,
    tyre_age: null,
    pit: null,
  })),
});

const race = {
  season: 2025,
  round: 2,
  total_laps: 3,
  neutralizations: [],
  drivers: [
    driver("VER", "Red Bull", 2, [
      [1, 1, 0],
      [2, 1, 0],
      [3, 1, 0],
    ]),
    driver("LEC", "Ferrari", 1, [
      [1, 2, 1.5],
      [2, 2, null],
      [3, 2, 2.25],
    ]),
    driver("HAM", "Ferrari", 0, [
      [1, 3, 4],
      [2, 3, 6],
    ]),
  ],
} as unknown as RaceLaps;
type Row = RaceLaps["drivers"][number];
const [ver, lec, ham] = race.drivers as [Row, Row, Row];

describe("race charts", () => {
  it("start the positions at the grid, a pit lane start at the back", () => {
    expect(positions(lec, 3)).toEqual([
      { lap: 0, value: 1 },
      { lap: 1, value: 2 },
      { lap: 2, value: 2 },
      { lap: 3, value: 2 },
    ]);
    expect(positions(ham, 3)[0]).toEqual({ lap: 0, value: 3 });
  });

  it("give the gap to the leader, or to a driver as the gaps tool does: the difference of their gaps", () => {
    expect(gaps(lec)).toEqual([
      { lap: 1, value: 1.5 },
      { lap: 3, value: 2.25 },
    ]);
    expect(gaps(ham, lec)).toEqual([{ lap: 1, value: 2.5 }]); // lap 2: LEC has no timing
    expect(gaps(ver, lec)[0]).toEqual({ lap: 1, value: -1.5 }); // ahead of the reference
  });

  it("break a line where a lap has no value", () => {
    const x = scale([0, 3], [0, 300]);
    const y = scale([0, 10], [0, 100]);
    expect(path(gaps(lec), x, y)).toBe("M100.0,15.0M300.0,22.5");
    expect(path(positions(lec, 3), x, y)).toBe("M0.0,10.0L100.0,20.0L200.0,20.0L300.0,20.0");
  });

  it("scale the axes to round ticks and to the highlighted drivers", () => {
    expect(ticks([0, 53], 10)).toEqual([0, 10, 20, 30, 40, 50]);
    expect(ticks([0, 2.4])).toEqual([0, 0.5, 1, 1.5, 2]);
    expect(gapDomain([gaps(lec), gaps(ver, lec)])).toEqual([-2.25, 2.25 + 4.5 * 0.05]);
    expect(gapDomain([])).toEqual([0, 1]);
    expect(lastLap(race)).toBe(3);
  });

  it("highlight the podium or the page's drivers, the second driver of a team dashed", () => {
    expect(defaultHighlight(race)).toEqual(["VER", "LEC", "HAM"]);
    expect(defaultHighlight(race, ["HAM", "XXX"])).toEqual(["HAM"]);
    expect([...dashed(race)]).toEqual(["HAM"]);
  });

  it("move the end labels apart, within the chart", () => {
    expect(spread([100, 50, 104], 12, [10, 330])).toEqual([100, 50, 112]);
    expect(spread([5, 6], 12, [10, 330])).toEqual([10, 22]); // under the top
    expect(spread([329, 330, 331], 12, [10, 330])).toEqual([306, 318, 330]); // pushed up from the bottom
  });
});
