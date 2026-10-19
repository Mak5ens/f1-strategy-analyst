"use client";

import { cn } from "cn";
import { type KeyboardEvent, type PointerEvent, useId, useMemo, useState } from "react";
import type { RaceLaps } from "@/lib/api/client";
import { formatLapTime, formatSeconds } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import {
  type DriverLaps,
  dashed,
  defaultHighlight,
  gapDomain,
  gaps,
  lastLap,
  type Point,
  path,
  positions,
  scale,
  ticks,
} from "@/lib/race-chart";
import { teamStyle } from "./driver-cell";
import { Panel, row, th, thead } from "./panel";

const t = getMessages().race.charts;
const compounds = getMessages().race.strategy.compounds;

// The drawing's own units: the SVG scales to its panel, which scrolls sideways on a phone rather than squeezing.
const W = 960;
const H = 340;
const M = { top: 12, right: 52, bottom: 28, left: 48 };

type Series = { driver: DriverLaps; points: Point[]; highlighted: boolean; dashed: boolean };

/**
 * The race lap by lap (LAB-189): positions from the grid, and the gaps at the line to the leader or to a chosen
 * driver. The highlighted drivers are drawn in their team's colour, the others faded; hovering or the arrow keys
 * read one lap in both charts at once, and a table gives the same numbers.
 */
export function RaceCharts({ race, focus = [] }: { race: RaceLaps; focus?: string[] }) {
  const initial = useMemo(() => defaultHighlight(race, focus), [race, focus]);
  const [highlight, setHighlight] = useState<string[]>(initial);
  const [lap, setLap] = useState<number | null>(null);
  const [reference, setReference] = useState<string>("");
  const second = useMemo(() => dashed(race), [race]);
  const total = lastLap(race);
  const drivers = race.drivers.filter((driver) => driver.laps.length > 0);
  const referenceDriver = drivers.find((driver) => driver.driver.code === reference);
  const shown = new Set(highlight);

  const series = (points: (driver: DriverLaps) => Point[]): Series[] =>
    drivers
      .map((driver) => ({
        driver,
        points: points(driver),
        highlighted: shown.has(driver.driver.code),
        dashed: second.has(driver.driver.code),
      }))
      // The highlighted drivers over the others.
      .toSorted((a, b) => Number(a.highlighted) - Number(b.highlighted));

  const starters = race.drivers.length;
  const positionSeries = series((driver) => positions(driver, starters));
  const gapSeries = series((driver) => gaps(driver, referenceDriver));
  const gapRange = gapDomain(gapSeries.filter((s) => s.highlighted).map((s) => s.points));

  const toggle = (code: string) =>
    setHighlight((codes) => (codes.includes(code) ? codes.filter((c) => c !== code) : [...codes, code]));

  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-3xl text-muted-foreground text-sm">{t.lead}</p>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-3 font-semibold text-muted-foreground text-xs uppercase tracking-wide">
          {t.drivers}
        </legend>
        <div className="flex flex-wrap gap-2">
          {drivers.map(({ driver }) => (
            <button
              key={driver.code}
              type="button"
              aria-pressed={shown.has(driver.code)}
              title={driver.name}
              onClick={() => toggle(driver.code)}
              style={teamStyle(driver.colour)}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-semibold text-xs transition-colors",
                "focus-visible:outline-2 focus-visible:outline-ring",
                shown.has(driver.code)
                  ? "border-[var(--team)] bg-surface-raised text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <span
                className={cn("h-3 w-1 rounded-full bg-[var(--team)]", !shown.has(driver.code) && "opacity-40")}
                aria-hidden
              />
              {driver.code}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setHighlight(initial)}
            className="rounded-full px-2.5 py-1 font-semibold text-primary text-xs hover:underline"
          >
            {t.reset}
          </button>
          <button
            type="button"
            onClick={() => setHighlight(drivers.map((driver) => driver.driver.code))}
            className="rounded-full px-2.5 py-1 font-semibold text-primary text-xs hover:underline"
          >
            {t.all}
          </button>
        </div>
      </fieldset>

      <Readout race={race} lap={lap} highlight={highlight} reference={referenceDriver} />

      <section className="flex flex-col gap-3">
        <div>
          <h3 className="display text-xl">{t.positions}</h3>
          <p className="text-muted-foreground text-sm">{t.positionsLead}</p>
        </div>
        <LapChart
          label={t.positions}
          race={race}
          total={total}
          series={positionSeries}
          domain={[1, starters]}
          yTicks={[1, 5, 10, 15, 20].filter((p) => p <= starters)}
          format={(value) => `P${value}`}
          labels
          lap={lap}
          onLap={setLap}
        />
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="display text-xl">{t.gaps}</h3>
            <p className="text-muted-foreground text-sm">{t.gapsLead(referenceDriver?.driver.name ?? null)}</p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t.reference}</span>
            <select
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              className="rounded-md border bg-surface px-2 py-1"
            >
              <option value="">{t.leader}</option>
              {drivers.map(({ driver }) => (
                <option key={driver.code} value={driver.code}>
                  {driver.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <LapChart
          label={t.gaps}
          race={race}
          total={total}
          series={gapSeries}
          domain={gapRange}
          yTicks={ticks(gapRange)}
          format={(value) => (value === 0 ? "0" : `${value > 0 ? "+" : ""}${value} ${t.seconds}`)}
          lap={lap}
          onLap={setLap}
        />
      </section>

      <p className="text-muted-foreground text-xs">{t.hint}</p>
      <LapTable race={race} highlight={highlight} reference={referenceDriver} />
    </div>
  );
}

/** One chart: laps across, the value down (position 1 or no gap at the top), the hovered lap marked. */
function LapChart({
  label,
  race,
  total,
  series,
  domain,
  yTicks,
  format,
  labels = false,
  lap,
  onLap,
}: {
  label: string;
  race: RaceLaps;
  total: number;
  series: Series[];
  domain: [number, number];
  yTicks: number[];
  format: (value: number) => string;
  labels?: boolean;
  lap: number | null;
  onLap: (lap: number | null) => void;
}) {
  const clip = useId();
  const x = scale([0, total], [M.left, W - M.right]);
  const y = scale(domain, [M.top, H - M.bottom]);
  const lapTicks = ticks([0, total], 10).filter((tick) => tick > 0);

  const lapAt = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const at = ((event.clientX - box.left) / box.width) * W;
    const value = Math.round(((at - M.left) / (W - M.left - M.right)) * total);
    onLap(Math.min(total, Math.max(1, value)));
  };
  const keys = (event: KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1, PageUp: 10, PageDown: -10 };
    const move = moves[event.key];
    if (move !== undefined) onLap(Math.min(total, Math.max(1, (lap ?? 0) + move)));
    else if (event.key === "Home") onLap(1);
    else if (event.key === "End") onLap(total);
    else if (event.key === "Escape") onLap(null);
    else return;
    event.preventDefault();
  };

  return (
    <Panel min="40rem" className="py-3">
      {/* Read lap by lap with the arrow keys: a slider over the laps, the drawing its picture. */}
      <div
        role="slider"
        aria-label={label}
        aria-valuemin={1}
        aria-valuemax={total}
        aria-valuenow={lap ?? 1}
        aria-valuetext={`${t.lap} ${lap ?? 1}`}
        tabIndex={0}
        onKeyDown={keys}
        className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <svg
          viewBox={`0 0 ${W} ${H}`}
          aria-hidden
          className="block h-auto w-full select-none"
          onPointerMove={lapAt}
          onPointerDown={lapAt}
          onPointerLeave={() => onLap(null)}
        >
          <defs>
            <clipPath id={clip}>
              <rect x={M.left} y={M.top - 4} width={W - M.left - M.right} height={H - M.top - M.bottom + 8} />
            </clipPath>
          </defs>
          {race.neutralizations.map((period) => (
            <rect
              key={`${period.kind}-${period.start_lap}`}
              data-neutralization={period.kind}
              x={x(period.start_lap - 1)}
              width={x(period.end_lap) - x(period.start_lap - 1)}
              y={M.top}
              height={H - M.top - M.bottom}
              className={period.kind === "red_flag" ? "fill-red-flag" : "fill-neutralized"}
            />
          ))}
          {yTicks.map((tick) => (
            <g key={tick} className="text-muted-foreground">
              <line x1={M.left} x2={W - M.right} y1={y(tick)} y2={y(tick)} stroke="currentColor" strokeOpacity={0.12} />
              <text x={M.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" fill="currentColor" fontSize={11}>
                {format(tick)}
              </text>
            </g>
          ))}
          {lapTicks.map((tick) => (
            <text key={tick} x={x(tick)} y={H - 8} textAnchor="middle" fontSize={11} className="fill-muted-foreground">
              {tick}
            </text>
          ))}
          <g clipPath={`url(#${clip})`}>
            {series.map(({ driver, points, highlighted, dashed: dash }) => (
              <g key={driver.driver.code} style={teamStyle(driver.driver.colour)} data-driver={driver.driver.code}>
                <path
                  d={path(points, x, y)}
                  fill="none"
                  stroke={highlighted ? "var(--team)" : "var(--muted-foreground)"}
                  strokeOpacity={highlighted ? 1 : 0.18}
                  strokeWidth={highlighted ? 2.25 : 1.25}
                  strokeDasharray={dash && highlighted ? "6 4" : undefined}
                  strokeLinejoin="round"
                />
                {highlighted &&
                  driver.laps
                    .filter((l) => l.pit === "in")
                    .map((l) => {
                      const point = points.find((p) => p.lap === l.lap);
                      return (
                        point && (
                          <circle
                            key={l.lap}
                            data-pit={l.lap}
                            cx={x(point.lap)}
                            cy={y(point.value)}
                            r={4}
                            className="fill-band"
                            stroke="var(--team)"
                            strokeWidth={2}
                          />
                        )
                      );
                    })}
              </g>
            ))}
          </g>
          {labels &&
            series
              .filter((s) => s.highlighted && s.points.length)
              .map(({ driver, points }) => {
                const end = points.at(-1);
                return (
                  end && (
                    <text
                      key={driver.driver.code}
                      x={x(end.lap) + 6}
                      y={y(end.value)}
                      dy="0.32em"
                      fontSize={11}
                      fontWeight={700}
                      style={teamStyle(driver.driver.colour)}
                      fill="var(--team)"
                    >
                      {driver.driver.code}
                    </text>
                  )
                );
              })}
          {lap !== null && (
            <g aria-hidden>
              <line
                x1={x(lap)}
                x2={x(lap)}
                y1={M.top}
                y2={H - M.bottom}
                className="stroke-foreground"
                strokeOpacity={0.5}
              />
              {series
                .filter((s) => s.highlighted)
                .map(({ driver, points }) => {
                  const point = points.find((p) => p.lap === lap);
                  return (
                    point && (
                      <circle
                        key={driver.driver.code}
                        cx={x(lap)}
                        cy={y(point.value)}
                        r={3.5}
                        style={teamStyle(driver.driver.colour)}
                        fill="var(--team)"
                      />
                    )
                  );
                })}
            </g>
          )}
        </svg>
      </div>
    </Panel>
  );
}

/** The hovered lap, driver by driver, for the highlighted ones: what both charts show at that point. */
function Readout({
  race,
  lap,
  highlight,
  reference,
}: {
  race: RaceLaps;
  lap: number | null;
  highlight: string[];
  reference?: DriverLaps;
}) {
  const rows = race.drivers
    .filter((driver) => highlight.includes(driver.driver.code))
    .map((driver) => ({
      driver,
      at: driver.laps.find((l) => l.lap === lap),
      gap: gaps(driver, reference).find((p) => p.lap === lap),
    }))
    .filter((row) => row.at)
    .toSorted((a, b) => (a.at?.position ?? 99) - (b.at?.position ?? 99));
  return (
    <div aria-live="polite" className="min-h-16 rounded-xl border bg-surface px-4 py-3 text-sm">
      {lap === null || !rows.length ? (
        <p className="text-muted-foreground">{t.hint}</p>
      ) : (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <span className="figures font-bold">
            {t.lap} {lap}
          </span>
          {rows.map(({ driver, at, gap }) => (
            <span key={driver.driver.code} className="flex items-center gap-2" style={teamStyle(driver.driver.colour)}>
              <span className="h-4 w-1 rounded-full bg-[var(--team)]" aria-hidden />
              <span className="font-semibold">{driver.driver.code}</span>
              <span className="figures text-muted-foreground">
                P{at?.position}
                {gap && gap.value !== 0 && ` · ${gap.value > 0 ? "+" : "−"}${formatSeconds(Math.abs(gap.value))}`}
                {at?.lap_time_s ? ` · ${formatLapTime(at.lap_time_s)}` : ""}
                {at?.compound ? ` · ${compounds[at.compound] ?? at.compound}` : ""}
                {at?.pit === "in" ? ` · ${t.pitIn}` : at?.pit === "out" ? ` · ${t.pitOut}` : ""}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** The same numbers as a table, lap by lap, for the highlighted drivers: the charts' accessible alternative. */
function LapTable({ race, highlight, reference }: { race: RaceLaps; highlight: string[]; reference?: DriverLaps }) {
  const drivers = race.drivers.filter((driver) => highlight.includes(driver.driver.code));
  const total = lastLap(race);
  const of = drivers.map((driver) => ({
    driver,
    laps: new Map(driver.laps.map((l) => [l.lap, l])),
    gaps: new Map(gaps(driver, reference).map((p) => [p.lap, p.value])),
  }));
  return (
    <details className="group">
      <summary className="cursor-pointer font-semibold text-primary text-sm">{t.table}</summary>
      <Panel min={`${8 + drivers.length * 9}rem`} className="mt-3 max-h-[28rem] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className={thead}>
            <tr className="border-b">
              <th className={cn(th, "text-left")}>{t.lap}</th>
              {drivers.map(({ driver }) => (
                <th key={driver.code} className={cn(th, "text-right")} style={teamStyle(driver.colour)}>
                  {driver.code}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="figures">
            {Array.from({ length: total }, (_, index) => index + 1).map((n) => (
              <tr key={n} className={row}>
                <td className="py-2 pr-4">{n}</td>
                {of.map(({ driver, laps, gaps: byLap }) => {
                  const at = laps.get(n);
                  const gap = byLap.get(n);
                  return (
                    <td key={driver.driver.code} className="py-2 pr-4 text-right">
                      {at?.position ? `P${at.position}` : "—"}
                      {gap !== undefined && gap !== 0 && (
                        <span className="text-muted-foreground">
                          {" "}
                          {gap > 0 ? "+" : "−"}
                          {formatSeconds(Math.abs(gap))}
                        </span>
                      )}
                      {at?.pit === "in" && <span className="text-muted-foreground"> · {t.pitIn}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </details>
  );
}
