"use client";

import { cn } from "cn";
import { useEffect, useState, useTransition } from "react";
import { type SimulationState, simulate } from "@/app/actions";
import type { RaceLaps, Simulation } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { gapDomain, lastLap, ticks } from "@/lib/race-chart";
import { teamStyle } from "./driver-cell";
import { LapChart, type Series } from "./race-charts";

const t = getMessages().race.simulator;
const seconds = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const signed = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});
const s = (value: number, format = seconds) => `${format.format(value)} s`;
const DRY = ["SOFT", "MEDIUM", "HARD"];
const compoundName = (compound: string | null) =>
  compound ? (getMessages().race.strategy.compounds[compound] ?? compound) : getMessages().race.strategy.unknown;

/**
 * Another strategy for a driver (LAB-213, LAB-214): each stop on another lap, each stint on another compound, projected by code at every change (the API's
 * `simulation`), next to the race as it was, with the error measured on real stints and what the model ignores.
 */
export function StrategySimulator({ race }: { race: RaceLaps }) {
  const drivers = race.drivers.filter((driver) => driver.laps.some((lap) => lap.pit === "in"));
  const [driver, setDriver] = useState(drivers[0]?.driver.code ?? "");
  const [rival, setRival] = useState(() => race.drivers[1]?.driver.code ?? "");
  const [stops, setStops] = useState<number[] | null>(null);
  const [compounds, setCompounds] = useState<(string | null)[] | null>(null);
  const [state, setState] = useState<SimulationState>({ result: null, error: null });
  // The driver's last projection: its stops and stints keep the controls up when a strategy asked is refused.
  const [controls, setControls] = useState<Simulation | null>(null);
  const [pending, start] = useTransition();
  const total = lastLap(race);

  useEffect(() => {
    if (!driver) return;
    const timer = setTimeout(
      () =>
        start(async () => {
          const next = await simulate(
            race.season,
            race.round,
            driver,
            stops,
            rival && rival !== driver ? rival : null,
            compounds,
          );
          setState(next);
          if (next.result) setControls(next.result);
        }),
      stops === null ? 0 : 250,
    );
    return () => clearTimeout(timer);
  }, [race.season, race.round, driver, stops, rival, compounds]);

  const { result, error } = state;
  const shown = stops ?? controls?.raced_stops ?? [];
  const select = "rounded-md border bg-surface px-3 py-2 text-sm";
  const pick = (code: string) => {
    setDriver(code);
    setStops(null);
    setCompounds(null);
    setControls(null);
  };
  const reset = () => {
    setStops(null);
    setCompounds(null);
  };
  const choose = (index: number, compound: string) =>
    setCompounds((current) =>
      (controls?.stints ?? []).map((_, at) => (at === index ? compound || null : (current?.[at] ?? null))),
    );
  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-3xl text-muted-foreground text-sm">{t.lead}</p>
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-muted-foreground text-xs uppercase tracking-wide">
          {t.driver}
          <select value={driver} onChange={(event) => pick(event.target.value)} className={select}>
            {drivers.map(({ driver: one }) => (
              <option key={one.code} value={one.code}>
                {one.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-muted-foreground text-xs uppercase tracking-wide">
          {t.rival}
          <select value={rival} onChange={(event) => setRival(event.target.value)} className={select}>
            <option value="">{t.leader}</option>
            {race.drivers
              .filter((one) => one.driver.code !== driver && one.laps.length)
              .map(({ driver: one }) => (
                <option key={one.code} value={one.code}>
                  {one.name}
                </option>
              ))}
          </select>
        </label>
        {(stops !== null || compounds?.some(Boolean)) && (
          <button type="button" onClick={reset} className="py-2 font-semibold text-primary text-sm">
            {t.reset}
          </button>
        )}
      </div>

      {controls && (
        <div className="flex flex-col gap-3">
          {shown.map((lap, index) => (
            <label key={controls.raced_stops[index]} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span className="w-20 font-semibold">{t.stop(index + 1)}</span>
              <input
                type="range"
                min={2}
                max={total - 1}
                value={lap}
                aria-label={`${t.stop(index + 1)}, ${t.inLap}`}
                onChange={(event) =>
                  setStops(shown.map((other, at) => (at === index ? Number(event.target.value) : other)))
                }
                className="w-64 max-w-full accent-[var(--primary)]"
              />
              <span className="figures w-16">
                {getMessages().race.charts.lap} {lap}
              </span>
              <span className="text-muted-foreground text-xs">{t.raced(controls.raced_stops[index] ?? lap)}</span>
            </label>
          ))}
          {controls.stints.map((stint, index) => (
            <label key={stint.raced_from} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span className="w-20 font-semibold">{t.stint(index + 1)}</span>
              <select
                value={compounds?.[index] ?? ""}
                onChange={(event) => choose(index, event.target.value)}
                aria-label={`${t.stint(index + 1)}, ${t.compound}`}
                className={select}
              >
                <option value="">{t.racedCompound(compoundName(stint.raced_compound))}</option>
                {DRY.filter((one) => one !== stint.raced_compound).map((one) => (
                  <option key={one} value={one}>
                    {compoundName(one)}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}

      <div aria-live="polite" className={cn("flex flex-col gap-6", pending && "opacity-60 transition-opacity")}>
        {error ? (
          <p className="rounded-xl border border-destructive/50 bg-surface p-4 text-sm">
            {error === "unreachable" ? t.unreachable : `${t.error} ${error}`}
          </p>
        ) : result ? (
          <Projection race={race} result={result} />
        ) : (
          <p className="text-muted-foreground text-sm">{t.loading}</p>
        )}
      </div>
    </div>
  );
}

function Projection({ race, result }: { race: RaceLaps; result: Simulation }) {
  const [lap, setLap] = useState<number | null>(null);
  const at = result.laps.find((one) => one.lap === lap);
  const end = result.laps.at(-1);
  const difference = result.time_difference_s;
  const error = result.expected_error;
  const driver = race.drivers.find((one) => one.driver.code === result.driver);
  const series: Series[] = [
    { label: "raced", colour: null, key: "raced_gap_s" as const },
    { label: "projected", colour: driver?.driver.colour ?? null, key: "projected_gap_s" as const },
  ].map(({ label, colour, key }) => ({
    driver: { driver: { code: label, name: label, team: null, colour }, grid: null, laps: [], pace: [] },
    points: result.laps.flatMap((lap) => (lap[key] === null ? [] : [{ lap: lap.lap, value: lap[key] as number }])),
    highlighted: label === "projected",
    dashed: false,
  }));
  const domain = gapDomain(series.map((one) => one.points));
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1 rounded-xl border bg-surface p-4">
          <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.difference}</span>
          <span className="figures display text-3xl">{difference === 0 ? "0 s" : s(difference, signed)}</span>
          <span className="text-muted-foreground text-xs">
            {difference === 0 ? t.same : difference < 0 ? t.gains(s(-difference)) : t.loses(s(difference))}
          </span>
        </div>
        {end && (
          <div className="flex flex-col gap-1 rounded-xl border bg-surface p-4">
            <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.finish}</span>
            <span className="figures display text-3xl" style={teamStyle(driver?.driver.colour)}>
              {end.raced_position !== null && end.projected_position !== null
                ? t.position(end.raced_position, end.projected_position)
                : "—"}
            </span>
            {end.raced_gap_s !== null && end.projected_gap_s !== null && (
              <span className="text-muted-foreground text-xs">
                {t.gap(s(end.raced_gap_s, signed), s(end.projected_gap_s, signed))}
              </span>
            )}
          </div>
        )}
      </div>

      <section className="flex flex-col gap-3">
        <p className="text-muted-foreground text-sm">
          {t.chart}
          {at && at.raced_gap_s !== null && at.projected_gap_s !== null
            ? ` · ${getMessages().race.charts.lap} ${at.lap} : ${t.gap(s(at.raced_gap_s, signed), s(at.projected_gap_s, signed))}`
            : ""}
        </p>
        <LapChart
          label={t.chart}
          race={race}
          total={lastLap(race)}
          series={series}
          domain={domain}
          yTicks={ticks(domain)}
          format={(value) => (value === 0 ? "0" : `${value > 0 ? "+" : ""}${value} s`)}
          lap={lap}
          onLap={setLap}
        />
      </section>

      <section className="flex flex-col gap-2 rounded-xl border bg-surface p-4 text-sm">
        <h3 className="font-semibold text-muted-foreground text-xs uppercase tracking-wide">{t.trust}</h3>
        {Math.abs(difference) < Math.max(error?.median_s ?? 0, result.compound_error?.median_s ?? 0) && (
          <p className="font-semibold text-warning">{t.tooSmall}</p>
        )}
        {error && (
          <p>
            {t.extended(
              result.extended_laps,
              error.laps_from,
              error.laps_to,
              s(error.median_s),
              s(error.p90_s),
              s(error.bias_s, signed),
              error.season,
            )}
          </p>
        )}
        {result.compound_error && (
          <p>
            {t.otherCompound(
              result.compound_error.laps_from,
              result.compound_error.laps_to,
              s(result.compound_error.median_s),
              s(result.compound_error.p90_s),
              result.compound_error.season,
            )}
          </p>
        )}
        {result.stints.map(
          (stint, index) =>
            stint.extrapolated_laps > 0 && (
              <p key={stint.asked_from} className="text-muted-foreground">
                {t.extrapolated(index + 1, stint.extrapolated_laps)}
              </p>
            ),
        )}
        <p className="text-muted-foreground">{t.lineError(s(result.model_error_s))}</p>
        <h3 className="mt-2 font-semibold text-muted-foreground text-xs uppercase tracking-wide">{t.assumptions}</h3>
        <ul className="list-disc pl-5 text-muted-foreground">
          {t.limits.map((limit) => (
            <li key={limit}>{limit}</li>
          ))}
        </ul>
      </section>
    </>
  );
}
