import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { RaceLaps } from "@/lib/api/client";
import { RaceCharts } from "./race-charts";

afterEach(cleanup);

const lap = (n: number, position: number, gap_s: number, pit: "in" | "out" | null = null) => ({
  lap: n,
  position,
  gap_s,
  lap_time_s: 90 + n,
  compound: n <= 2 ? "MEDIUM" : "HARD",
  tyre_age: n,
  pit,
});
const race = {
  season: 2025,
  round: 2,
  total_laps: 4,
  neutralizations: [{ kind: "safety_car", start_lap: 2, end_lap: 3, duration_s: 200 }],
  drivers: [
    {
      driver: { code: "VER", name: "Max Verstappen", team: "Red Bull", colour: "#3671c6" },
      grid: 2,
      laps: [lap(1, 1, 0), lap(2, 1, 0, "in"), lap(3, 2, 1.2, "out"), lap(4, 1, 0)],
    },
    {
      driver: { code: "LEC", name: "Charles Leclerc", team: "Ferrari", colour: "#e8002d" },
      grid: 1,
      laps: [lap(1, 2, 0.8), lap(2, 2, 1.5), lap(3, 1, 0), lap(4, 2, 2.4)],
    },
    {
      driver: { code: "HUL", name: "Nico Hülkenberg", team: "Kick Sauber", colour: null },
      grid: 3,
      laps: [],
    },
  ],
} as unknown as RaceLaps;

describe("RaceCharts", () => {
  it("draws the drivers who raced, the neutralizations across their laps and the stops", () => {
    const { container } = render(<RaceCharts race={race} />);
    expect(screen.queryByRole("button", { name: "HUL" })).toBeNull(); // no lap: nothing to draw
    const band = container.querySelector('[data-neutralization="safety_car"]');
    // Laps 2 to 3 run from x = 1 to x = 3 of 4 laps, over 860 units from 48.
    expect(band?.getAttribute("x")).toBe(String(48 + 860 / 4));
    expect(band?.getAttribute("width")).toBe(String(860 / 2));
    expect(
      [...container.querySelectorAll('[data-driver="VER"] [data-pit]')].map((c) => c.getAttribute("data-pit")),
    ).toEqual(
      ["2", "2"], // one in-lap, in each chart
    );
  });

  it("reads a lap with the keyboard, gaps to the chosen driver as in the table", () => {
    render(<RaceCharts race={race} />);
    const positions = screen.getAllByRole("slider")[0] as HTMLElement;
    fireEvent.keyDown(positions, { key: "End" });
    expect(positions.getAttribute("aria-valuetext")).toBe("Tour 4");
    const readout = screen.getByText("Tour 4").parentElement as HTMLElement;
    expect(within(readout).getByText(/P2 · \+2,4 s/)).toBeTruthy(); // LEC, 2.4 s behind the leader

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "LEC" } });
    expect(within(readout).getByText(/P1 · −2,4 s/)).toBeTruthy(); // VER, 2.4 s ahead of LEC
    fireEvent.click(screen.getByText("Voir les données tour par tour"));
    const cells = screen.getAllByRole("row").at(-1)?.querySelectorAll("td");
    expect([...(cells ?? [])].map((cell) => cell.textContent)).toEqual(["4", "P1 −2,4 s", "P2"]);
  });

  it("highlights a driver from the list", () => {
    const { container } = render(<RaceCharts race={race} focus={["LEC"]} />);
    const ver = screen.getByRole("button", { name: "VER" });
    expect(ver.getAttribute("aria-pressed")).toBe("false");
    expect(container.querySelector('[data-driver="VER"] path')?.getAttribute("stroke-opacity")).toBe("0.18");
    fireEvent.click(ver);
    expect(ver.getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelector('[data-driver="VER"] path')?.getAttribute("stroke-opacity")).toBe("1");
  });
});
