import type { SeasonOverview } from "@/lib/api/client";

/** Two rounds of a season, for the season page's tests. */
export const season = {
  season: 2025,
  form_rounds: 5,
  rounds: [
    { round: 1, grand_prix: "Grand Prix d'Australie", sprint: false },
    { round: 2, grand_prix: "Grand Prix de Chine", sprint: true },
  ],
  drivers: [
    {
      driver: { code: "NOR", name: "Lando Norris", team: "McLaren", colour: "#ff8000" },
      position: 1,
      points: 44,
      wins: 1,
      form_points: 44,
      cumulative: [25, 44],
      positions: [1, 1],
      results: [
        { text: "1", position: 1, grid: 1, points: 25 },
        { text: "2", position: 2, grid: 2, points: 19 },
      ],
    },
    {
      driver: { code: "VER", name: "Max Verstappen", team: "Red Bull Racing", colour: "#3671c6" },
      position: 2,
      points: 18,
      wins: 0,
      form_points: 18,
      cumulative: [18, 18],
      positions: [2, 2],
      results: [{ text: "2", position: 2, grid: 3, points: 18 }, null],
    },
  ],
  teams: [
    {
      team: "McLaren",
      colour: "#ff8000",
      position: 1,
      points: 44,
      wins: 1,
      cumulative: [25, 44],
      positions: [1, 1],
      qualifying_gap_pct: [0, 0.2],
      race_gap_pct: [0, null],
    },
    {
      team: "Red Bull Racing",
      colour: "#3671c6",
      position: 2,
      points: 18,
      wins: 0,
      cumulative: [18, 18],
      positions: [2, 2],
      qualifying_gap_pct: [0.3, 0],
      race_gap_pct: [0.5, 0.4],
    },
  ],
} as SeasonOverview;
