import { cn } from "cn";
import type { Race } from "@/lib/api/client";
import { formatPoints } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import { DriverCell, teamStyle } from "./driver-cell";
import { PlacesGained } from "./grid-table";
import { Panel, row, th, thead } from "./panel";

const t = getMessages().race.standings;

/** The championships as they stood after this round, with the places each gained or lost with it. */
export function StandingsTables({ race }: { race: Race }) {
  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <section className="flex flex-col gap-4">
        <Heading title={t.drivers} round={race.summary.round} />
        <Panel min="22rem">
          <table className="w-full text-left text-sm">
            <thead className={thead}>
              <tr className="border-b">
                <th className={cn(th, "w-12")}>{getMessages().race.result.position}</th>
                <th className={th}>{getMessages().race.result.driver}</th>
                <th className={cn(th, "text-right")}>{t.points}</th>
                <th className="w-14 py-4 text-right font-semibold" aria-label={getMessages().race.grid.change} />
              </tr>
            </thead>
            <tbody>
              {race.driver_standings.map((standing) => (
                <tr key={standing.driver.code} className={row}>
                  <td className="display figures py-3 pr-4 text-base">{standing.position ?? "–"}</td>
                  <td className="py-3 pr-4">
                    <DriverCell driver={standing.driver} />
                  </td>
                  <td className="figures py-3 pr-4 text-right font-semibold">{formatPoints(standing.points)}</td>
                  <td className="py-3 text-right text-xs">
                    <PlacesGained places={standing.change} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </section>
      <section className="flex flex-col gap-4">
        <Heading title={t.teams} round={race.summary.round} />
        <Panel min="22rem">
          <table className="w-full text-left text-sm">
            <thead className={thead}>
              <tr className="border-b">
                <th className={cn(th, "w-12")}>{getMessages().race.result.position}</th>
                <th className={th}>{getMessages().race.result.team}</th>
                <th className={cn(th, "text-right")}>{t.points}</th>
                <th className="w-14 py-4 text-right font-semibold" aria-label={getMessages().race.grid.change} />
              </tr>
            </thead>
            <tbody>
              {race.team_standings.map((standing) => (
                <tr key={standing.team} className={row}>
                  <td className="display figures py-3 pr-4 text-base">{standing.position ?? "–"}</td>
                  <td className="py-3 pr-4">
                    <span className="flex items-center gap-3 font-semibold" style={teamStyle(standing.colour)}>
                      <span className="h-6 w-1 rounded-full bg-[var(--team)]" aria-hidden />
                      {standing.team}
                    </span>
                  </td>
                  <td className="figures py-3 pr-4 text-right font-semibold">{formatPoints(standing.points)}</td>
                  <td className="py-3 text-right text-xs">
                    <PlacesGained places={standing.change} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </section>
    </div>
  );
}

function Heading({ title, round }: { title: string; round: number }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <h3 className="display text-lg">{title}</h3>
      <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.after(round)}</span>
    </div>
  );
}
