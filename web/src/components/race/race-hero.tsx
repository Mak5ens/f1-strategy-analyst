import { cn } from "cn";
import type { ReactNode } from "react";
import type { Race, RaceSummary } from "@/lib/api/client";
import { formatDate, formatLapTime, formatTemperature } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import { teamStyle } from "./driver-cell";

const t = getMessages().race;

/**
 * The top of a race's page, on a black band in the winner's colour: the round, the Grand Prix, the place and the
 * date, the round number huge and faint where a photo would be; then the race in a few big figures.
 */
export function RaceHero({ summary, race }: { summary: RaceSummary; race?: Race }) {
  return (
    <section className="relative overflow-hidden border-b bg-band" style={teamStyle(summary.winner?.colour)}>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(110deg,color-mix(in_oklab,var(--team)_28%,transparent)_0%,transparent_45%)]"
      />
      <span
        aria-hidden
        className="display figures pointer-events-none absolute -right-4 -bottom-10 text-[11rem] text-watermark italic sm:-bottom-16 sm:text-[18rem]"
      >
        {String(summary.round).padStart(2, "0")}
      </span>
      <div className="relative mx-auto flex max-w-6xl flex-col gap-4 px-4 pt-12 pb-10 sm:pt-16">
        <p className="flex items-center gap-2 font-semibold text-primary-text text-sm uppercase tracking-wider">
          <span className="slash" aria-hidden />
          {t.round(summary.round, summary.season)}
          {summary.sprint && <span className="text-muted-foreground">· {t.sprint}</span>}
        </p>
        <h1 className="display text-4xl sm:text-6xl">{summary.grand_prix}</h1>
        <p className="text-lg text-muted-foreground">
          {summary.location}
          {summary.date && ` · ${formatDate(summary.date)}`}
        </p>
        {race && summary.winner && <Figures race={race} />}
      </div>
    </section>
  );
}

function Figures({ race }: { race: Race }) {
  const winner = race.summary.winner;
  const periods = race.neutralizations.length;
  const figures: { label: string; value: ReactNode; detail?: string; className?: string }[] = [
    { label: t.figures.winner, value: winner?.name, detail: winner?.team ?? undefined },
    {
      label: t.figures.fastestLap,
      value: race.fastest_lap ? formatLapTime(race.fastest_lap.lap_time_s) : "–",
      detail: race.fastest_lap
        ? `${race.fastest_lap.driver.name} · ${getMessages().race.strategy.lap} ${race.fastest_lap.lap}`
        : undefined,
      className: "text-fastest",
    },
    { label: t.figures.laps, value: race.total_laps ?? "–" },
    { label: t.figures.neutralizations, value: periods },
  ];
  if (race.weather) {
    figures.push({
      label: t.figures.weather,
      value: `${formatTemperature(race.weather.air_temp_max_c)} / ${formatTemperature(race.weather.track_temp_max_c)}`,
      detail: race.weather.rainfall ? t.figures.rain : t.figures.dry,
    });
  }
  return (
    <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-6 border-t pt-6 sm:grid-cols-3 lg:grid-cols-5">
      {figures.map((figure) => (
        <div key={figure.label} className="min-w-0">
          <dt className="text-muted-foreground text-xs uppercase tracking-wide">{figure.label}</dt>
          <dd className={cn("display figures mt-1.5 text-xl leading-tight sm:text-2xl", figure.className)}>
            {figure.value}
          </dd>
          {figure.detail && <dd className="mt-1 truncate text-muted-foreground text-sm">{figure.detail}</dd>}
        </div>
      ))}
    </dl>
  );
}
