import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { DebriefSummary, Subject } from "@/lib/api/client";
import { DebriefCard } from "./debrief-card";
import { subjectFor, subjectTitle } from "./subject-line";

afterEach(cleanup);

const ferrari: Subject = {
  season: 2025,
  round: 16,
  grand_prix: "Grand Prix d'Italie",
  kind: "team",
  teams: ["Ferrari"],
  focus: [{ code: "LEC", name: "Charles Leclerc", team: "Ferrari", colour: "#e8002d" }],
  colour: "#e8002d",
};
const unresolved: Subject = {
  ...ferrari,
  season: null,
  round: null,
  grand_prix: null,
  kind: null,
  teams: [],
  focus: [],
  colour: null,
};

function waiting(subject: Subject, stop: DebriefSummary["waiting"]): DebriefSummary {
  const at = "2026-10-15T18:00:00Z";
  return {
    id: "d1",
    request: "Débrief du dernier GP",
    status: "waiting",
    waiting: stop,
    subject,
    created_at: at,
    updated_at: at,
  };
}

describe("the subject of a debrief", () => {
  it("names the Grand Prix and who the debrief is for", () => {
    expect(subjectTitle(ferrari)).toBe("Grand Prix d'Italie 2025");
    expect(subjectFor(ferrari)).toBe("Ferrari");
    expect(subjectFor({ ...ferrari, kind: "race", teams: [] })).toBe("Toute la course");
  });

  it("says the race is still to be chosen", () => {
    expect(subjectTitle(unresolved)).toBe("Course à préciser");
  });
});

describe("DebriefCard", () => {
  it("shows the stop it waits at and links to the request", () => {
    render(<DebriefCard debrief={waiting(ferrari, "plan")} now={new Date("2026-10-15T18:05:00Z")} />);
    expect(screen.getByText("Plan à valider")).toBeDefined();
    expect(screen.getByText("Valider le plan →")).toBeDefined();
    expect(screen.getByText("il y a 5 minutes")).toBeDefined();
    expect(screen.getByRole("link").getAttribute("href")).toBe("/debriefs/d1");
  });

  it("shows the request itself while the race is unknown", () => {
    render(<DebriefCard debrief={waiting(unresolved, "clarification")} />);
    expect(screen.getByText("Débrief du dernier GP")).toBeDefined();
    expect(screen.queryByText("Toute la course")).toBeNull();
  });
});
