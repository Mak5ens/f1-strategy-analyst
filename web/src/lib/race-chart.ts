import type { RaceLaps } from "@/lib/api/client";

/**
 * What the race charts draw, computed from the API's laps (LAB-189), without a chart library: the series, the scales
 * and the domains are plain functions, tested on their own, and the components only draw them in SVG.
 *
 * A lap n is run between x = n - 1 and x = n: a driver's point for lap n sits at x = n, the line where its timing
 * reads it, and the grid at x = 0. A neutralization of laps 10 to 14 covers x = 9 to 14.
 */

export type DriverLaps = RaceLaps["drivers"][number];
export type Point = { lap: number; value: number };

/** A linear scale from a domain to a range: `scale([0, 50], [0, 960])(25)` is 480. */
export function scale([d0, d1]: [number, number], [r0, r1]: [number, number]) {
  const ratio = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (value: number) => r0 + (value - d0) * ratio;
}

/** The SVG path through points, broken where a lap has no value rather than joined across the gap. */
export function path(points: Point[], x: (lap: number) => number, y: (value: number) => number): string {
  let previous: number | null = null;
  return points
    .map(({ lap, value }) => {
      const command = previous !== null && lap === previous + 1 ? "L" : "M";
      previous = lap;
      return `${command}${x(lap).toFixed(1)},${y(value).toFixed(1)}`;
    })
    .join("");
}

/** Positions lap by lap, from the grid at lap 0; a pit lane start at the back of the grid. */
export function positions(driver: DriverLaps, starters: number): Point[] {
  const grid = driver.grid === 0 ? starters : driver.grid;
  const laps = driver.laps.flatMap((lap) => (lap.position === null ? [] : [{ lap: lap.lap, value: lap.position }]));
  return grid ? [{ lap: 0, value: grid }, ...laps] : laps;
}

/**
 * The gap to a reference lap by lap, in seconds, positive behind it: each driver's gap to the leader at the line
 * less the reference's, as the `gaps` tool computes the gap between two drivers. No reference: the leader.
 */
export function gaps(driver: DriverLaps, reference?: DriverLaps): Point[] {
  const theirs = new Map(reference?.laps.map((lap) => [lap.lap, lap.gap_s]));
  return driver.laps.flatMap((lap) => {
    const base = reference ? theirs.get(lap.lap) : 0;
    if (lap.gap_s === null || base === null || base === undefined) return [];
    return [{ lap: lap.lap, value: Math.round((lap.gap_s - base) * 1000) / 1000 }];
  });
}

/** The laps a chart spans: the scheduled distance, or the longest race of the drivers. */
export function lastLap(race: RaceLaps): number {
  return Math.max(race.total_laps ?? 0, ...race.drivers.flatMap((driver) => driver.laps.map((lap) => lap.lap)), 1);
}

/** Round ticks for a domain: about `count` of them, at 1, 2 or 5 times a power of ten. */
export function ticks([min, max]: [number, number], count = 5): number[] {
  const span = max - min;
  if (span <= 0) return [min];
  const raw = span / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * power).find((candidate) => candidate >= raw) ?? raw;
  const first = Math.ceil(min / step) * step;
  return Array.from(
    { length: Math.floor((max - first) / step) + 1 },
    (_, i) => Math.round((first + i * step) * 1e6) / 1e6,
  );
}

/** The gap axis: what the highlighted drivers span, at least 0 to 1 s, a little room under the slowest. */
export function gapDomain(series: Point[][]): [number, number] {
  const values = series.flat().map((point) => point.value);
  if (!values.length) return [0, 1];
  const min = Math.min(0, ...values);
  const max = Math.max(1, ...values);
  return [min, max + (max - min) * 0.05];
}

/** The drivers drawn first: the podium, or the drivers the page is about; never one who ran no lap. */
export function defaultHighlight(race: RaceLaps, focus: string[] = []): string[] {
  const raced = race.drivers.filter((driver) => driver.laps.length > 0);
  const known = new Set(raced.map((driver) => driver.driver.code));
  const chosen = focus.filter((code) => known.has(code));
  return chosen.length ? chosen : raced.slice(0, 3).map((driver) => driver.driver.code);
}

/** The second driver of a team draws dashed: teammates share a colour. */
export function dashed(race: RaceLaps): Set<string> {
  const seen = new Set<string>();
  const second = new Set<string>();
  for (const { driver } of race.drivers) {
    const team = driver.team ?? driver.code;
    if (seen.has(team)) second.add(driver.code);
    seen.add(team);
  }
  return second;
}

export type StintLine = { stint: number; compound: string | null; from: Point; to: Point; degradation: number | null };

/**
 * A driver's pace: the clean laps the `degradation` tool fits, and each stint's fitted line on the raw lap times,
 * from its first clean lap to its last, at the tyre age of each (`raw_slope_s_per_lap`, `raw_intercept_s`).
 */
export function pace(driver: DriverLaps): { dots: Point[]; lines: StintLine[] } {
  const laps = new Map(driver.laps.map((lap) => [lap.lap, lap]));
  const dots: Point[] = [];
  const lines: StintLine[] = [];
  for (const stint of driver.pace) {
    const used = stint.laps.flatMap((n) => {
      const lap = laps.get(n);
      return lap?.lap_time_s ? [{ lap: n, value: lap.lap_time_s, age: lap.tyre_age ?? n }] : [];
    });
    dots.push(...used.map(({ lap, value }) => ({ lap, value })));
    const first = used[0];
    const last = used.at(-1);
    const { raw_slope_s_per_lap: slope, raw_intercept_s: intercept } = stint;
    if (first && last && slope !== null && intercept !== null && last.lap > first.lap) {
      const at = (point: { lap: number; age: number }) => ({ lap: point.lap, value: intercept + slope * point.age });
      lines.push({
        stint: stint.stint,
        compound: stint.compound,
        from: at(first),
        to: at(last),
        degradation: stint.degradation_s_per_lap,
      });
    }
  }
  return { dots: dots.toSorted((a, b) => a.lap - b.lap), lines };
}

/** The lap time axis: the highlighted drivers' clean laps, a few tenths of room around them. */
export function paceDomain(series: Point[][]): [number, number] {
  const values = series.flat().map((point) => point.value);
  if (!values.length) return [0, 1];
  return [Math.min(...values) - 0.3, Math.max(...values) + 0.3];
}

/**
 * The end labels' heights, moved apart so that none overlaps: in order down the chart, each at least `gap` under the
 * one above, then the whole column pulled back within [top, bottom]. Two teammates a tenth apart stay readable.
 */
export function spread(ys: number[], gap: number, [top, bottom]: [number, number]): number[] {
  const order = ys.map((y, index) => ({ y, index })).toSorted((a, b) => a.y - b.y);
  const placed: number[] = [];
  for (const [rank, { y }] of order.entries()) {
    placed.push(Math.max(y, top, rank > 0 ? (placed[rank - 1] ?? top) + gap : top));
  }
  // Too low: push the column up from the bottom, as far as it needs.
  for (let rank = placed.length - 1; rank >= 0; rank--) {
    const below = rank === placed.length - 1 ? bottom : (placed[rank + 1] ?? bottom) - gap;
    placed[rank] = Math.min(placed[rank] ?? bottom, below);
  }
  const result = new Array<number>(ys.length);
  for (const [rank, { index }] of order.entries()) result[index] = placed[rank] ?? 0;
  return result;
}
