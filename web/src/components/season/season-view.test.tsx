import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { season } from "@/lib/season.fixture";
import { ChampionshipChart, ResultsGrid, SeasonSummary, TeamPace } from "./season-view";

afterEach(cleanup);

describe("SeasonView", () => {
  it("sums the season up: the leader and their lead, the rounds, the team, the form", () => {
    render(<SeasonSummary season={season} />);
    expect(screen.getByText("26 pts d'avance sur Max Verstappen")).toBeTruthy();
    expect(screen.getByText("dont 1 avec sprint")).toBeTruthy();
    expect(screen.getByText("McLaren")).toBeTruthy();
  });

  it("reads a round of the championship with the keyboard, and switches to the teams", () => {
    const { container } = render(<ChampionshipChart season={season} />);
    const chart = screen.getByRole("slider");
    fireEvent.keyDown(chart, { key: "Home" });
    expect(screen.getByRole("status").textContent).toBe(
      "Après la manche 1 · Grand Prix d'Australie · NOR 25 pts · VER 18 pts",
    );
    expect([...container.querySelectorAll("[data-label]")].map((label) => label.textContent)).toEqual(["NOR", "VER"]);
    fireEvent.click(screen.getByRole("button", { name: "Équipes" }));
    expect(screen.getByRole("button", { name: "Red Bull Racing" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("lays each driver's results out round by round, each round a link to its race", () => {
    render(<ResultsGrid season={season} />);
    expect(screen.getByRole("link", { name: "2" }).getAttribute("href")).toBe("/grand-prix/2025/2");
    const verstappen = screen.getByText("VER").closest("tr") as HTMLElement;
    expect([...verstappen.querySelectorAll("[data-tone]")].map((cell) => cell.getAttribute("data-tone"))).toEqual([
      "podium",
      "none",
    ]);
  });

  it("ranks the teams by their median gap to the fastest", () => {
    render(<TeamPace season={season} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0] as HTMLElement).getByText("McLaren")).toBeTruthy();
    expect(within(rows[1] as HTMLElement).getByText("0,45 %")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Qualifications" }));
    expect(within(screen.getAllByRole("row")[1] as HTMLElement).getByText("0,10 %")).toBeTruthy();
  });
});
