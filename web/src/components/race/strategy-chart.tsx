import { cn } from "cn";
import type { Race } from "@/lib/api/client";
import { formatSeconds } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import { teamStyle } from "./driver-cell";
import { Panel, row, th, thead } from "./panel";

const t = getMessages().race.strategy;

// Each compound's colour token, and a dark letter on the light ones.
const compounds: Record<string, { bar: string; letter: string }> = {
  SOFT: { bar: "bg-soft text-white", letter: "S" },
  MEDIUM: { bar: "bg-medium text-band", letter: "M" },
  HARD: { bar: "bg-hard text-band", letter: "H" },
  INTERMEDIATE: { bar: "bg-intermediate text-white", letter: "I" },
  WET: { bar: "bg-wet text-white", letter: "W" },
};
const unknown = { bar: "bg-surface-raised text-muted-foreground", letter: "?" };

function percent(laps: number, total: number) {
  return `${(laps / total) * 100}%`;
}

/**
 * The tyre strategy of every driver, lap by lap: one bar per stint in the compound's colour, a set already used
 * striped. Safety car and VSC laps are yellow bands across every row, red flags red ones.
 */
export function StrategyChart({ race }: { race: Race }) {
  const total = Math.max(
    race.total_laps ?? 0,
    ...race.strategies.flatMap((s) => s.stints.map((stint) => stint.end_lap)),
  );
  const ticks = Array.from({ length: Math.floor(total / 10) }, (_, index) => (index + 1) * 10);
  const used = Object.entries(compounds).filter(([name]) =>
    race.strategies.some((strategy) => strategy.stints.some((stint) => stint.compound === name)),
  );
  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-sm">{t.lead}</p>
      <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
        {used.map(([name, style]) => (
          <li key={name} className="flex items-center gap-2">
            <span
              className={cn("figures grid size-5 place-items-center rounded-full font-bold text-[0.65rem]", style.bar)}
            >
              {style.letter}
            </span>
            {t.compounds[name]}
          </li>
        ))}
      </ul>
      <Panel min="34rem" className="py-4">
        <div className="grid grid-cols-[3.5rem_1fr] gap-x-3">
          <div />
          <div className="relative mb-2 h-4 text-muted-foreground text-xs">
            {ticks.map((lap) => (
              <span key={lap} className="figures absolute -translate-x-1/2" style={{ left: percent(lap - 0.5, total) }}>
                {lap}
              </span>
            ))}
          </div>
          {race.strategies.map((strategy) => (
            <div key={strategy.driver.code} className="contents">
              <span
                className="flex items-center gap-2 font-semibold text-xs"
                style={teamStyle(strategy.driver.colour)}
                title={strategy.driver.name}
              >
                <span className="h-4 w-1 rounded-full bg-[var(--team)]" aria-hidden />
                {strategy.driver.code}
              </span>
              <div className="relative h-7 border-white/5 border-b">
                {race.neutralizations.map((period) => (
                  <span
                    key={`${period.kind}-${period.start_lap}`}
                    aria-hidden
                    className={cn("absolute inset-y-0", period.kind === "red_flag" ? "bg-red-flag" : "bg-neutralized")}
                    style={{
                      left: percent(period.start_lap - 1, total),
                      width: percent(period.end_lap - period.start_lap + 1, total),
                    }}
                  />
                ))}
                {strategy.stints.map((stint) => {
                  const style = compounds[stint.compound ?? ""] ?? unknown;
                  return (
                    <span
                      key={stint.stint}
                      className={cn(
                        "figures absolute inset-y-1 flex items-center overflow-hidden rounded-[4px] px-1.5 font-bold text-[0.65rem]",
                        style.bar,
                        stint.fresh === false &&
                          "bg-[repeating-linear-gradient(135deg,transparent_0_4px,rgb(0_0_0/0.18)_4px_8px)]",
                      )}
                      style={{
                        left: `calc(${percent(stint.start_lap - 1, total)} + 1px)`,
                        width: `calc(${percent(stint.laps, total)} - 2px)`,
                      }}
                      title={`${t.compounds[stint.compound ?? ""] ?? t.unknown} · ${t.lap} ${stint.start_lap}–${stint.end_lap}${stint.fresh === false ? ` · ${t.used}` : ""}`}
                    >
                      {stint.laps >= 3 && style.letter}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Panel>
      <StopsTable race={race} />
    </div>
  );
}

/** Every pit stop, in lap order: time in the pit lane, stopped, and what it cost against normal laps. */
function StopsTable({ race }: { race: Race }) {
  const stops = race.strategies
    .flatMap((strategy) => strategy.stops.map((stop) => ({ ...stop, driver: strategy.driver })))
    .toSorted((a, b) => a.lap - b.lap);
  if (!stops.length) return null;
  return (
    <div className="mt-8 flex flex-col gap-4">
      <h3 className="display text-lg">{t.stops}</h3>
      <Panel min="34rem">
        <table className="w-full text-left text-sm">
          <thead className={thead}>
            <tr className="border-b">
              <th className={th}>{t.lap}</th>
              <th className={th}>{getMessages().race.result.driver}</th>
              <th className={th}>{t.stop}</th>
              <th className={cn(th, "text-right")}>{t.pitLane}</th>
              <th className={cn(th, "text-right")}>{t.stationary}</th>
              <th className="py-4 text-right font-semibold">{t.lost}</th>
            </tr>
          </thead>
          <tbody>
            {stops.map((stop) => (
              <tr key={`${stop.driver.code}-${stop.stop_number}`} className={row}>
                <td className="display figures py-3 pr-4 text-base">{stop.lap}</td>
                <td className="py-3 pr-4">
                  <span className="flex items-center gap-2 font-semibold" style={teamStyle(stop.driver.colour)}>
                    <span className="h-4 w-1 rounded-full bg-[var(--team)]" aria-hidden />
                    {stop.driver.name}
                  </span>
                </td>
                <td className="py-3 pr-4 text-muted-foreground">
                  {stop.stop_number} → {t.compounds[stop.compound_after ?? ""] ?? t.unknown}
                </td>
                <td className="figures py-3 pr-4 text-right">
                  {stop.pit_lane_time_s != null ? formatSeconds(stop.pit_lane_time_s) : "–"}
                </td>
                <td className="figures py-3 pr-4 text-right">
                  {stop.stationary_time_s != null ? formatSeconds(stop.stationary_time_s) : "–"}
                </td>
                <td className="figures py-3 text-right font-semibold">
                  {stop.time_lost_s != null ? formatSeconds(stop.time_lost_s) : "–"}
                  {stop.neutralized && (
                    <span className="block font-normal text-warning text-xs">{t.neutralizedStop}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
