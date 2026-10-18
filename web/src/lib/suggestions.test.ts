import { describe, expect, it } from "vitest";
import type { Race } from "@/lib/api/client";
import { raceSuggestions } from "./suggestions";

const driver = (code: string, name: string) => ({ code, name, team: null, colour: null });
const stint = (compound: string) => ({ stint: 1, compound, start_lap: 1, end_lap: 10, laps: 10, fresh: true });
const stop = (lap: number, neutralized: boolean) => ({
  stop_number: 1,
  lap,
  pit_lane_time_s: 20,
  stationary_time_s: 2.5,
  time_lost_s: 20,
  compound_after: "HARD",
  neutralized,
});

const race = {
  summary: { winner: driver("NOR", "Lando Norris") },
  strategies: [
    { driver: driver("NOR", "Lando Norris"), stints: [stint("MEDIUM")], stops: [stop(20, false)] },
    { driver: driver("VER", "Max Verstappen"), stints: [stint("MEDIUM")], stops: [stop(30, true)] },
    { driver: driver("HAM", "Lewis Hamilton"), stints: [stint("SOFT")], stops: [stop(12, false)] },
  ],
  penalties: [{ driver: driver("OCO", "Esteban Ocon"), kind: "time", seconds: 5, reason: "", lap: 9 }],
  classification: [{ driver: driver("HAM", "Lewis Hamilton"), places_gained: 6 }],
} as unknown as Race;

describe("raceSuggestions", () => {
  it("asks what the race raises, the odd start first", () => {
    expect(raceSuggestions(race)).toEqual([
      "Pourquoi un départ en pneus tendres pour Lewis Hamilton ?",
      "L'arrêt de Max Verstappen sous neutralisation au tour 30 a-t-il payé ?",
      "Combien la pénalité de 5 s a-t-elle coûté à Esteban Ocon ?",
      "D'où viennent les 6 places gagnées par Lewis Hamilton ?",
    ]);
  });

  it("still has the win to ask about on a quiet race", () => {
    const quiet = { ...race, strategies: race.strategies.slice(0, 1), penalties: [], classification: [] } as Race;
    expect(raceSuggestions(quiet)).toEqual(["Qu'est-ce qui a fait la victoire de Lando Norris ?"]);
  });
});
