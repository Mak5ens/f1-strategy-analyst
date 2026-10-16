import type { Race } from "@/lib/api/client";
import { formatSeconds } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import { teamStyle } from "./driver-cell";

const t = getMessages().race.events;

/** What interrupted or judged the race: safety cars, VSC, red flags, and the stewards' penalties, in lap order. */
export function RaceEvents({ race }: { race: Race }) {
  const periods = race.neutralizations.map((period) => ({
    lap: period.start_lap,
    key: `${period.kind}-${period.start_lap}`,
    tone: period.kind === "red_flag" ? "bg-primary" : "bg-warning",
    title: t.kinds[period.kind],
    detail: `${t.laps(period.start_lap, period.end_lap)} · ${formatSeconds(period.duration_s)}`,
    colour: null as string | null,
  }));
  const penalties = race.penalties.map((penalty) => ({
    lap: penalty.lap,
    key: `${penalty.driver.code}-${penalty.lap}-${penalty.kind}`,
    tone: "bg-[var(--team)]",
    title: `${t.penalty(penalty.seconds, penalty.kind)} · ${penalty.driver.name}`,
    detail: `${penalty.reason}, ${t.penaltyLap(penalty.lap)}`,
    colour: penalty.driver.colour,
  }));
  const events = [...periods, ...penalties].toSorted((a, b) => a.lap - b.lap);
  return (
    <aside className="rounded-xl border bg-surface p-5">
      <h3 className="display mb-4 text-lg">{t.title}</h3>
      {events.length ? (
        <ol className="flex flex-col gap-4">
          {events.map((event) => (
            <li key={event.key} className="flex gap-3" style={teamStyle(event.colour)}>
              <span className={`mt-1.5 size-2.5 shrink-0 rounded-full ${event.tone}`} aria-hidden />
              <div>
                <p className="font-semibold text-sm">{event.title}</p>
                <p className="text-muted-foreground text-sm">{event.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-muted-foreground text-sm">{t.none}</p>
      )}
    </aside>
  );
}
