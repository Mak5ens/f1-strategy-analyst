import Link from "next/link";
import type { RaceSummary } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import { teamStyle } from "./driver-cell";

const t = getMessages();

/** The last race, in large: the Grand Prix, its place and date, its winner, in the winner's team colour. */
export function LatestRace({ race }: { race: RaceSummary }) {
  return (
    <Link
      href={`/grand-prix/${race.season}/${race.round}`}
      style={teamStyle(race.winner?.colour)}
      className="group relative flex min-h-64 flex-col justify-end overflow-hidden rounded-xl border bg-surface bg-[linear-gradient(110deg,color-mix(in_oklab,var(--team)_50%,transparent)_0%,transparent_60%)] p-6 transition duration-200 hover:border-[color-mix(in_oklab,var(--team)_60%,transparent)] sm:p-8"
    >
      <span
        aria-hidden
        className="display figures pointer-events-none absolute -right-4 -bottom-10 text-[10rem] text-white/[0.05] italic sm:-bottom-14 sm:text-[15rem]"
      >
        {String(race.round).padStart(2, "0")}
      </span>
      <div className="relative flex flex-col gap-3">
        <p className="font-semibold text-sm uppercase tracking-wider">
          {t.race.round(race.round, race.season)}
          {race.date && <span className="text-muted-foreground"> · {formatDate(race.date)}</span>}
        </p>
        <h3 className="display text-3xl sm:text-5xl">{race.grand_prix}</h3>
        <p className="text-muted-foreground">{race.location}</p>
        {race.winner && (
          <p className="mt-2 flex items-center gap-2 font-semibold">
            <span className="slash" aria-hidden />
            <span className="sr-only">{t.calendar.winner} :</span>
            {race.winner.name}
            <span className="font-normal text-muted-foreground">· {race.winner.team}</span>
          </p>
        )}
        <p className="mt-3 font-semibold text-primary text-sm transition-transform group-hover:translate-x-1">
          {t.home.seeRace} →
        </p>
      </div>
    </Link>
  );
}
