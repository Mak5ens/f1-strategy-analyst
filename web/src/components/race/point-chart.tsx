"use client";

import Link from "next/link";
import { useState } from "react";
import type { FactChart, RaceLaps } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { dashed, gapDomain, gaps, lastLap, type Point, pace, paceDomain, positions, ticks } from "@/lib/race-chart";
import { teamStyle } from "./driver-cell";
import { formatShortLapTime, LapChart, type Series } from "./race-charts";

const t = getMessages().race.charts;

/**
 * The chart of the numbers a debrief's point cites (LAB-189): the chart the API names for its analysis, the drivers
 * it is about highlighted, zoomed on its laps; a link opens the whole race on the GP page.
 */
export function PointChart({ race, chart, label }: { race: RaceLaps; chart: FactChart; label: string }) {
  const [lap, setLap] = useState<number | null>(null);
  const drivers = race.drivers.filter((driver) => driver.laps.length > 0);
  const reference = drivers.find((driver) => driver.driver.code === chart.reference);
  const second = dashed(race);
  const points = (driver: (typeof drivers)[number]): Point[] =>
    chart.kind === "gaps"
      ? gaps(driver, reference)
      : chart.kind === "pace"
        ? pace(driver).dots
        : positions(driver, race.drivers.length);
  const series: Series[] = drivers
    .map((driver) => ({
      driver,
      points: points(driver),
      highlighted: chart.drivers.includes(driver.driver.code),
      dashed: second.has(driver.driver.code),
    }))
    .filter((one) => one.highlighted || chart.kind === "positions")
    .toSorted((a, b) => Number(a.highlighted) - Number(b.highlighted));
  const from = chart.from_lap ?? 1;
  const total = chart.to_lap ?? lastLap(race);
  const shown = series
    .filter((one) => one.highlighted)
    .map((one) => one.points.filter((point) => point.lap >= from - 1 && point.lap <= total));
  const domain: [number, number] =
    chart.kind === "positions"
      ? [1, race.drivers.length]
      : chart.kind === "pace"
        ? paceDomain(shown)
        : gapDomain(shown);
  const format =
    chart.kind === "positions"
      ? (value: number) => `P${value}`
      : chart.kind === "pace"
        ? formatShortLapTime
        : (value: number) => (value === 0 ? "0" : `${value > 0 ? "+" : ""}${value} ${t.seconds}`);
  const href = `/grand-prix/${race.season}/${race.round}?onglet=course&pilotes=${chart.drivers.join(",")}`;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground text-xs">
        {t.pointChart[chart.kind]}
        {reference && chart.kind === "gaps" ? ` ${reference.driver.name}` : ""}
        {chart.from_lap && chart.to_lap ? ` · ${t.lapsLower(chart.from_lap, chart.to_lap)}` : ""}
        {lap !== null ? ` · ${t.lap} ${lap}` : ""}
      </p>
      <LapChart
        label={label}
        race={race}
        from={from}
        total={total}
        series={series}
        domain={domain}
        yTicks={chart.kind === "positions" ? [1, 5, 10, 15, 20] : ticks(domain)}
        format={format}
        labels={chart.kind !== "pace"}
        line={chart.kind !== "pace"}
        lap={lap}
        onLap={setLap}
        overlay={
          chart.kind === "pace"
            ? (x, y) =>
                series
                  .filter((one) => one.highlighted)
                  .flatMap(({ driver }) =>
                    pace(driver).lines.map((stint) => (
                      <line
                        key={`${driver.driver.code}-${stint.stint}`}
                        style={teamStyle(driver.driver.colour)}
                        x1={x(stint.from.lap)}
                        y1={y(stint.from.value)}
                        x2={x(stint.to.lap)}
                        y2={y(stint.to.value)}
                        stroke="var(--team)"
                        strokeWidth={2}
                      />
                    )),
                  )
            : undefined
        }
      />
      <Link href={href} className="self-start font-semibold text-primary text-xs hover:underline">
        {t.openRace} →
      </Link>
    </div>
  );
}
