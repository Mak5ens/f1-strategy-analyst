import type { Subject } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().subject;

/** Who the debrief is for: the team, the drivers, the whole race, or its moments (LAB-204). */
export function subjectFor(subject: Subject): string {
  if (subject.moments) return t.moments;
  if (subject.kind === "team" && subject.teams.length) return subject.teams.join(", ");
  if (subject.kind === "driver") return subject.focus.map((driver) => driver.name).join(", ");
  return t.race;
}

/** The Grand Prix and its season, or that the race is still to be chosen. */
export function subjectTitle(subject: Subject): string {
  return subject.grand_prix && subject.season ? `${subject.grand_prix} ${subject.season}` : t.unresolved;
}

/** A debrief's title: the question asked, for a question on a race; the Grand Prix otherwise. */
export function debriefTitle(debrief: { request: string; subject: Subject }): string {
  return debrief.subject.question ? debrief.request : subjectTitle(debrief.subject);
}
