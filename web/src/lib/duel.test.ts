import { describe, expect, it } from "vitest";
import type { Driver, Duel } from "@/lib/api/client";
import { defaultPair, duelColours, favours } from "./duel";

const driver = (code: string, team: string, colour = "#e8002d"): Driver => ({ code, name: code, team, colour });
const drivers = [driver("NOR", "McLaren", "#ff8000"), driver("VER", "Red Bull"), driver("PIA", "McLaren", "#ff8000")];

describe("duel", () => {
  it("shows the pair asked, else the leader and their teammate", () => {
    expect(defaultPair(drivers, ["ver", "pia"])).toEqual(["VER", "PIA"]);
    expect(defaultPair(drivers, ["VER", "VER"])).toEqual(["NOR", "PIA"]);
    expect(defaultPair(drivers, ["XXX", "VER"])).toEqual(["NOR", "PIA"]);
    expect(defaultPair([driver("NOR", "McLaren"), driver("VER", "Red Bull")])).toEqual(["NOR", "VER"]);
    expect(defaultPair([])).toBeNull();
  });

  it("tells teammates apart and says who a gap favours", () => {
    const duel = { first: drivers[0], second: drivers[2] } as unknown as Duel;
    expect(duelColours(duel)).toEqual(["#ff8000", "var(--foreground)"]);
    expect(favours(duel, -0.2)?.code).toBe("NOR");
    expect(favours(duel, 0.2)?.code).toBe("PIA");
    expect(favours(duel, 0)).toBeNull();
    expect(favours(duel, null)).toBeNull();
  });
});
