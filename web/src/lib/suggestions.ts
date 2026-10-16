import type { Race } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().race.question;

/**
 * Questions the race itself raises, read from its data: a start on a compound few chose, a stop under a safety car,
 * a penalty, the most places gained, the win. Four at most, the most telling first.
 */
export function raceSuggestions(race: Race, count = 4): string[] {
  const suggestions: string[] = [];
  const starts = race.strategies.map((strategy) => strategy.stints[0]?.compound).filter((c): c is string => !!c);
  const usual = mostCommon(starts);
  const odd = race.strategies.find((strategy) => {
    const compound = strategy.stints[0]?.compound;
    return compound && compound !== usual && t.compounds[compound];
  });
  if (odd?.stints[0]?.compound) {
    suggestions.push(t.startOn(odd.driver.name, t.compounds[odd.stints[0].compound] ?? odd.stints[0].compound));
  }
  for (const strategy of race.strategies) {
    const stop = strategy.stops.find((s) => s.neutralized);
    if (stop) {
      suggestions.push(t.neutralizedStop(strategy.driver.name, stop.lap));
      break;
    }
  }
  const penalty = race.penalties[0];
  if (penalty) suggestions.push(t.penalty(penalty.driver.name, t.penaltyWhat(penalty.seconds)));
  const climber = race.classification
    .filter((entry) => (entry.places_gained ?? 0) >= 3)
    .toSorted((a, b) => (b.places_gained ?? 0) - (a.places_gained ?? 0))[0];
  if (climber?.places_gained) suggestions.push(t.gained(climber.driver.name, climber.places_gained));
  if (race.summary.winner) suggestions.push(t.win(race.summary.winner.name));
  return suggestions.slice(0, count);
}

function mostCommon(values: string[]): string | undefined {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts.entries()].toSorted((a, b) => b[1] - a[1])[0]?.[0];
}
