import type { SeasonOverview } from "@/lib/api/client";

/**
 * The season page's readings (LAB-215), as plain functions: the lines of its charts, who they show by default, and
 * how a result reads.
 */

export type Line = { code: string; label: string; colour: string | null; values: (number | null)[] };

/** The championship's lines, drivers or teams: points after each round. */
export function championship(season: SeasonOverview, kind: "drivers" | "teams"): Line[] {
  return kind === "drivers"
    ? season.drivers.map((one) => ({
        code: one.driver.code,
        label: one.driver.name,
        colour: one.driver.colour,
        values: one.cumulative,
      }))
    : season.teams.map((one) => ({ code: one.team, label: one.team, colour: one.colour, values: one.cumulative }));
}

/** The teams' pace lines, qualifying or race: the gap to the fastest after each round, in %. */
export function pace(season: SeasonOverview, kind: "qualifying" | "race"): Line[] {
  return season.teams.map((one) => ({
    code: one.team,
    label: one.team,
    colour: one.colour,
    values: kind === "qualifying" ? one.qualifying_gap_pct : one.race_gap_pct,
  }));
}

/** The first `count` in championship order: the lines a chart highlights first. */
export function leaders(lines: Line[], count = 5): string[] {
  return lines.slice(0, count).map((line) => line.code);
}

/** The median of the values measured, and how many; null when none is. */
export function median(values: (number | null)[]): { value: number; count: number } | null {
  const found = values.filter((value): value is number => value !== null).toSorted((a, b) => a - b);
  if (!found.length) return null;
  const middle = Math.floor(found.length / 2);
  const value = found.length % 2 ? (found[middle] ?? 0) : ((found[middle - 1] ?? 0) + (found[middle] ?? 0)) / 2;
  return { value, count: found.length };
}

/** How a race result reads in the grid: a win, a podium, points, no points, or out of the race. */
export function tone(result: { position: number | null } | null): string {
  if (!result) return "none";
  if (result.position === null) return "out";
  if (result.position === 1) return "win";
  if (result.position <= 3) return "podium";
  return result.position <= 10 ? "points" : "plain";
}
