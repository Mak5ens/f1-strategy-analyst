import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RaceLaps, Simulation } from "@/lib/api/client";
import { StrategySimulator } from "./strategy-simulator";

const simulate = vi.fn();
vi.mock("@/app/actions", () => ({ simulate: (...args: unknown[]) => simulate(...args) }));

afterEach(() => {
  cleanup();
  simulate.mockReset();
});

const driver = (code: string, name: string, pit: boolean) => ({
  driver: { code, name, team: code, colour: null },
  grid: 1,
  laps: [{ lap: 10, position: 1, gap_s: 0, lap_time_s: 90, compound: "MEDIUM", tyre_age: 10, pit: pit ? "in" : null }],
  pace: [],
});
const race = {
  season: 2025,
  round: 4,
  total_laps: 57,
  neutralizations: [],
  events: [],
  drivers: [driver("PIA", "Oscar Piastri", true), driver("RUS", "George Russell", true)],
} as unknown as RaceLaps;

const projection = (difference: number): Simulation =>
  ({
    driver: "PIA",
    rival: "RUS",
    raced_stops: [14, 32],
    stops: [19, 32],
    stints: [
      {
        compound: "SOFT",
        raced_compound: "SOFT",
        raced_from: 1,
        raced_to: 14,
        asked_from: 1,
        asked_to: 19,
        degradation_s_per_lap: 0.1,
        extrapolated_laps: 5,
      },
    ],
    time_difference_s: difference,
    laps: [
      { lap: 57, difference_s: 0, raced_gap_s: -15.5, projected_gap_s: -10, raced_position: 1, projected_position: 1 },
    ],
    model_error_s: 0.21,
    extended_laps: 5,
    expected_error: {
      laps_from: 1,
      laps_to: 5,
      samples: 3740,
      median_s: 0.81,
      p90_s: 3.06,
      bias_s: -0.19,
      season: 2025,
    },
    notes: [],
  }) as unknown as Simulation;

describe("StrategySimulator", () => {
  it("projects the raced strategy first, against the second driver, with the error measured", async () => {
    simulate.mockResolvedValue({ result: projection(5.5), error: null });
    render(<StrategySimulator race={race} />);
    await waitFor(() => expect(screen.getByText("+5,5 s")).toBeTruthy());
    expect(simulate).toHaveBeenCalledWith(2025, 4, "PIA", null, "RUS", null);
    expect(screen.getByText("P1, inchangé")).toBeTruthy();
    expect(screen.getByText(/se trompent de 0,8 s en médiane/)).toBeTruthy();
    expect(screen.getByText(/Relais 1 : 5 tours au-delà/)).toBeTruthy();
    expect(screen.getAllByRole("slider", { name: /Arrêt/ })).toHaveLength(2);
    expect(screen.queryByText(/ne permet pas de conclure/)).toBeNull();
  });

  it("says when the difference is smaller than the error, and why a strategy cannot be projected", async () => {
    simulate.mockResolvedValue({ result: projection(0.4), error: null });
    const { unmount } = render(<StrategySimulator race={race} />);
    await waitFor(() => expect(screen.getByText(/ne permet pas de conclure/)).toBeTruthy());
    unmount();

    simulate.mockResolvedValue({ result: null, error: "les tours d’arrêt doivent se suivre, du tour 2 au tour 56." });
    render(<StrategySimulator race={race} />);
    await waitFor(() =>
      expect(screen.getByText(/ne peut pas être projetée : les tours d’arrêt doivent se suivre/)).toBeTruthy(),
    );
  });

  it("asks for a stint on another compound, keeping the controls when it is refused", async () => {
    simulate.mockResolvedValue({ result: projection(5.5), error: null });
    render(<StrategySimulator race={race} />);
    const stint = await screen.findByRole("combobox", { name: "Relais 1, composé" });
    expect([...stint.querySelectorAll("option")].map((option) => option.textContent)).toEqual([
      "Tendre (couru)",
      "Medium",
      "Dur",
    ]);
    simulate.mockResolvedValue({ result: null, error: "trop peu de pilotes ont couru en tendres et en durs." });
    fireEvent.change(stint, { target: { value: "HARD" } });
    await waitFor(() => expect(simulate).toHaveBeenLastCalledWith(2025, 4, "PIA", null, "RUS", ["HARD"]));
    await screen.findByText(/ne peut pas être projetée : trop peu de pilotes/);
    expect(screen.getByRole("combobox", { name: "Relais 1, composé" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Revenir à la stratégie courue" }));
    await waitFor(() => expect(simulate).toHaveBeenLastCalledWith(2025, 4, "PIA", null, "RUS", null));
  });
});
