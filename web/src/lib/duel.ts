import type { Driver, Duel } from "@/lib/api/client";

/**
 * The duel page's choices and readings (LAB-212), as plain functions: the pair shown by default, the colours of two
 * drivers, and who a gap favours.
 */

/** The pair asked if both raced the season; else the season's leader and their teammate, or the first two. */
export function defaultPair(drivers: Driver[], asked: (string | undefined)[] = []): [string, string] | null {
  const codes = new Set(drivers.map((driver) => driver.code));
  const [a, b] = asked.map((code) => code?.toUpperCase());
  if (a && b && a !== b && codes.has(a) && codes.has(b)) return [a, b];
  const [leader] = drivers;
  if (!leader) return null;
  const teammate = drivers.find((driver) => driver !== leader && driver.team && driver.team === leader.team);
  const other = teammate ?? drivers[1];
  return other ? [leader.code, other.code] : null;
}

/** Each driver's colour: their team's, the second in the text colour when teammates share it. */
export function duelColours(duel: Duel): [string, string] {
  const first = duel.first.colour ?? "var(--primary)";
  const second =
    duel.second.colour && duel.second.colour !== duel.first.colour ? duel.second.colour : "var(--foreground)";
  return [first, second];
}

/** Who a gap (first driver's time less the second's) favours: the faster one, or nobody on a tie. */
export function favours(duel: Duel, gap: number | null | undefined): Driver | null {
  if (gap === null || gap === undefined || gap === 0) return null;
  return gap < 0 ? duel.first : duel.second;
}
