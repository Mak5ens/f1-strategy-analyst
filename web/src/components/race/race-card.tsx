import { cn } from "cn";
import Link from "next/link";
import type { RaceSummary } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import { teamStyle } from "./driver-cell";

const t = getMessages().calendar;

/** A round of the calendar: the Grand Prix, its place and date, its winner in the team's colour. */
export function RaceCard({ race }: { race: RaceSummary }) {
  return (
    <Link
      href={`/grand-prix/${race.season}/${race.round}`}
      style={teamStyle(race.winner?.colour)}
      className={cn(
        "group relative flex min-h-44 flex-col justify-between gap-5 overflow-hidden rounded-xl border bg-surface p-5",
        race.winner &&
          "bg-[linear-gradient(115deg,color-mix(in_oklab,var(--team)_40%,transparent)_0%,transparent_50%)]",
        "transition duration-200 hover:-translate-y-0.5 hover:border-[color-mix(in_oklab,var(--team)_60%,transparent)]",
      )}
    >
      <span
        aria-hidden
        className="display figures pointer-events-none absolute -right-2 -bottom-6 text-[7rem] text-white/[0.04] italic"
      >
        {String(race.round).padStart(2, "0")}
      </span>
      <div className="flex items-start justify-between gap-3 text-xs">
        <span className="font-semibold text-muted-foreground uppercase tracking-wide">
          {getMessages().subject.round(race.round)}
        </span>
        <span className="flex items-center gap-2">
          {race.sprint && (
            <span className="rounded-full bg-band/70 px-2.5 py-0.5 font-semibold uppercase tracking-wide">
              {t.sprint}
            </span>
          )}
          {race.date && <span className="text-muted-foreground">{formatDate(race.date)}</span>}
        </span>
      </div>
      <div className="relative">
        <h3 className="display text-xl leading-tight">
          {race.grand_prix.replace(/^Grand Prix (d'|de |du |des )/, "")}
        </h3>
        <p className="mt-1 text-muted-foreground text-sm">{race.location}</p>
        <p className="mt-3 flex items-center gap-2 font-semibold text-sm">
          {race.winner ? (
            <>
              <span className="slash" aria-hidden />
              <span className="sr-only">{t.winner} :</span>
              {race.winner.name}
            </>
          ) : (
            <span className="font-normal text-muted-foreground">{t.toCome}</span>
          )}
        </p>
      </div>
    </Link>
  );
}
