import { cn } from "cn";
import Link from "next/link";
import type { CSSProperties } from "react";
import { debriefTitle, subjectFor } from "@/components/subject-line";
import type { DebriefSummary } from "@/lib/api/client";
import { formatAgo } from "@/lib/format";
import { getMessages } from "@/lib/i18n";

const t = getMessages();

/**
 * A request waiting for the analyst: a band of its team's colour fading into the card, the stop it waits at, the
 * race, and who it is for. The round number, very large and faint, stands where a photo would.
 */
export function DebriefCard({ debrief, now }: { debrief: DebriefSummary; now?: Date }) {
  const { subject } = debrief;
  const stop = debrief.waiting ? t.stops[debrief.waiting] : null;
  return (
    <Link
      href={`/debriefs/${debrief.id}`}
      style={{ "--team": subject.colour ?? "var(--muted-foreground)" } as CSSProperties}
      className={cn(
        "group relative flex min-h-56 flex-col justify-between gap-6 overflow-hidden rounded-xl border bg-surface p-5",
        "bg-[linear-gradient(115deg,color-mix(in_oklab,var(--team)_55%,transparent)_0%,transparent_55%)]",
        "transition duration-200 hover:-translate-y-0.5 hover:border-[color-mix(in_oklab,var(--team)_60%,transparent)]",
      )}
    >
      {subject.round != null && (
        <span
          aria-hidden
          className="display figures pointer-events-none absolute -right-2 -bottom-6 text-[8rem] text-white/[0.04] italic"
        >
          {String(subject.round).padStart(2, "0")}
        </span>
      )}
      <div className="flex items-start justify-between gap-3">
        {stop && (
          <span className="rounded-full bg-band/70 px-3 py-1 font-semibold text-xs uppercase tracking-wide">
            {stop.label}
          </span>
        )}
        <span className="text-muted-foreground text-xs">{formatAgo(debrief.updated_at, now)}</span>
      </div>
      <div className="relative">
        <p className="text-muted-foreground text-xs">
          {subject.round != null ? `${t.subject.round(subject.round)} · ${subject.season}` : debrief.request}
        </p>
        <h3 className={cn("mt-1.5 leading-tight", subject.question ? "font-semibold text-lg" : "display text-xl")}>
          {debriefTitle(debrief)}
        </h3>
        {subject.grand_prix && (
          <p className="mt-2 flex items-center gap-2 font-semibold text-sm">
            <span className="slash" aria-hidden />
            {subjectFor(subject)}
          </p>
        )}
        {stop && (
          <p className="mt-4 font-semibold text-primary text-sm transition-transform group-hover:translate-x-1">
            {stop.action} →
          </p>
        )}
      </div>
    </Link>
  );
}
