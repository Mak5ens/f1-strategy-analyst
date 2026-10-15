import { cn } from "cn";
import type { Race } from "@/lib/api/client";
import { formatGap, formatLapTime, formatPoints, formatRaceTime } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import { DriverCell } from "./driver-cell";
import { Panel, row, th, thead } from "./panel";

const t = getMessages().race.result;

/** The classification: position, driver, laps, time or gap, each driver's best lap (the fastest in purple), points. */
export function ResultTable({ race }: { race: Race }) {
  const best = new Map(race.best_laps.map((lap) => [lap.driver.code, lap]));
  const fastest = race.fastest_lap?.driver.code;
  return (
    <Panel>
      <table className="w-full text-left text-sm">
        <thead className={thead}>
          <tr className="border-b">
            <th className={cn(th, "w-12")}>{t.position}</th>
            <th className={th}>{t.driver}</th>
            <th className={cn(th, "text-right")}>{t.laps}</th>
            <th className={cn(th, "text-right")}>{t.time}</th>
            <th className={cn(th, "text-right")}>{t.bestLap}</th>
            <th className="py-4 text-right font-semibold">{t.points}</th>
          </tr>
        </thead>
        <tbody>
          {race.classification.map((entry) => {
            const lap = best.get(entry.driver.code);
            return (
              <tr key={entry.driver.code} className={row}>
                <td className="display figures py-3 pr-4 text-base">
                  {t.positions[entry.position_text] ?? entry.position_text}
                </td>
                <td className="py-3 pr-4">
                  <DriverCell driver={entry.driver} />
                </td>
                <td className="figures py-3 pr-4 text-right text-muted-foreground">{entry.laps ?? "–"}</td>
                <td className="figures py-3 pr-4 text-right">
                  {entry.time_s != null
                    ? formatRaceTime(entry.time_s)
                    : entry.gap_s != null
                      ? formatGap(entry.gap_s)
                      : entry.laps_behind != null
                        ? t.lapsBehind(entry.laps_behind)
                        : entry.status
                          ? (t.statuses[entry.status] ?? entry.status)
                          : "–"}
                </td>
                <td
                  className={cn(
                    "figures py-3 pr-4 text-right",
                    entry.driver.code === fastest ? "font-semibold text-fastest" : "text-muted-foreground",
                  )}
                  title={entry.driver.code === fastest ? t.fastest : undefined}
                >
                  {lap ? formatLapTime(lap.lap_time_s) : "–"}
                </td>
                <td className="figures py-3 text-right font-semibold">
                  {entry.points ? formatPoints(entry.points) : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}
