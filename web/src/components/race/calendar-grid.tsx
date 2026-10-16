import { cn } from "cn";
import Link from "next/link";
import type { RaceSummary } from "@/lib/api/client";
import { shortName } from "@/lib/format";
import { getMessages } from "@/lib/i18n";
import { teamStyle } from "./driver-cell";

const t = getMessages();

/** A season at a glance: one small tile per round, its winner's colour as a bar, a click from its page. */
export function CalendarGrid({ races }: { races: RaceSummary[] }) {
  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
      {races.map((race) => (
        <li key={race.round}>
          <Link
            href={`/grand-prix/${race.season}/${race.round}`}
            style={teamStyle(race.winner?.colour)}
            className={cn(
              "flex h-full flex-col gap-1 rounded-lg border-l-4 border-l-[var(--team)] bg-band px-3 py-2.5 transition-colors hover:bg-surface",
              !race.winner && "border-l-white/10",
            )}
          >
            <span className="figures text-muted-foreground text-xs">{String(race.round).padStart(2, "0")}</span>
            <span className="truncate font-semibold text-sm">{shortName(race.grand_prix)}</span>
            <span className="truncate text-muted-foreground text-xs">{race.winner?.name ?? t.calendar.toCome}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
