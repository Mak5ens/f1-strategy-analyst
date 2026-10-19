import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Race } from "@/lib/api/client";
import { StrategyChart } from "./strategy-chart";

afterEach(cleanup);

const leclerc = { code: "LEC", name: "Charles Leclerc", team: "Ferrari", colour: "#e8002d" };
const race = {
  summary: { season: 2025, round: 16, grand_prix: "Grand Prix d'Italie" },
  total_laps: 50,
  neutralizations: [{ kind: "safety_car", start_lap: 10, end_lap: 14, duration_s: 400 }],
  strategies: [
    {
      driver: leclerc,
      stints: [
        { stint: 1, compound: "MEDIUM", start_lap: 1, end_lap: 25, laps: 25, fresh: true },
        { stint: 2, compound: "HARD", start_lap: 26, end_lap: 50, laps: 25, fresh: false },
      ],
      stops: [
        {
          stop_number: 1,
          lap: 25,
          pit_lane_time_s: 24.3,
          stationary_time_s: 2.0,
          time_lost_s: 21.04,
          compound_after: "HARD",
          neutralized: false,
        },
      ],
    },
  ],
} as unknown as Race;

describe("StrategyChart", () => {
  it("draws each stint across its laps, a used set said so", () => {
    const { container } = render(<StrategyChart race={race} />);
    const hard = screen.getByTitle("Dur · Tour 26–50 · pneus déjà utilisés");
    expect(hard.style.left).toBe("calc(50% + 1px)");
    expect(hard.style.width).toBe("calc(50% - 2px)");
    expect(container.querySelector(".bg-neutralized")?.getAttribute("style")).toContain("left: 18%");
  });

  it("says each compound by its letter and its name, not by its colour alone", () => {
    const short = structuredClone(race);
    const [strategy] = short.strategies;
    strategy?.stints.splice(1, 0, { stint: 3, compound: "SOFT", start_lap: 26, end_lap: 27, laps: 2, fresh: true });
    render(<StrategyChart race={short} />);
    const soft = screen.getByRole("img", { name: "Tendre · Tour 26–27" });
    expect(soft.textContent).toBe("S");
    expect(screen.getByRole("img", { name: "Medium · Tour 1–25" }).textContent).toBe("M");
  });

  it("lists the stops with what they cost, in French", () => {
    render(<StrategyChart race={race} />);
    expect(screen.getByText("21,0 s")).toBeDefined();
    expect(screen.getByText("1 → Dur")).toBeDefined();
  });
});
