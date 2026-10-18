import { cn } from "cn";
import Link from "next/link";
import type { CSSProperties } from "react";
import { subjectFor } from "@/components/subject-line";
import type { DebriefSummary } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().race.prepared;

/** Where a prepared debrief stands: readable once published, "en relecture" while it waits for its review. */
function state(debrief: DebriefSummary): { label: string; ready: boolean } {
  if (debrief.status === "published") return { label: t.read, ready: true };
  if (debrief.status === "stopped") return { label: t.stopped, ready: false };
  return { label: t.reviewing, ready: false };
}

/** One prepared debrief: the team's colour on its edge, who it is about, and whether it can be read yet. */
function Tile({ debrief, lead }: { debrief: DebriefSummary; lead?: string }) {
  const { label, ready } = state(debrief);
  return (
    <Link
      href={`/debriefs/${debrief.id}`}
      style={{ "--team": debrief.subject.colour ?? "var(--primary)" } as CSSProperties}
      className={cn(
        "group flex items-center justify-between gap-4 rounded-xl border border-l-4 border-l-[var(--team)] bg-surface",
        lead ? "px-5 py-4" : "px-4 py-3",
        "transition hover:-translate-y-0.5",
        !ready && "opacity-70",
      )}
    >
      <span className="flex flex-col gap-1">
        <span className={cn("font-semibold", lead ? "display text-xl" : "text-base")}>
          {subjectFor(debrief.subject)}
        </span>
        {lead && <span className="text-muted-foreground text-sm">{lead}</span>}
      </span>
      <span
        className={cn(
          "shrink-0 rounded-full px-2.5 py-1 font-semibold text-xs uppercase tracking-wide",
          ready ? "bg-primary/15 text-primary" : "bg-band text-muted-foreground",
        )}
      >
        {label}
      </span>
    </Link>
  );
}

/** The debriefs `just debriefs-prepare` wrote after the race (LAB-204): its moments, then each team and driver. */
export function PreparedDebriefs({ debriefs }: { debriefs: DebriefSummary[] }) {
  // In the order the batch wrote them: the teams by their best car's finishing place.
  const of = (category: string) =>
    debriefs
      .filter((debrief) => debrief.subject.prepared === category)
      .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const groups = [
    { id: "team", title: t.team, items: of("team") },
    { id: "driver", title: t.driver, items: of("driver") },
  ].filter((group) => group.items.length > 0);
  const moments = of("moments");
  return (
    <div className="flex flex-col gap-8">
      <p className="max-w-2xl text-muted-foreground">{t.lead}</p>
      {moments.map((debrief) => (
        <Tile key={debrief.id} debrief={debrief} lead={t.momentsLead} />
      ))}
      {groups.map((group) => (
        <div key={group.id} className="flex flex-col gap-3">
          <h3 className="font-semibold text-primary text-xs uppercase tracking-wider">{group.title}</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.items.map((debrief) => (
              <Tile key={debrief.id} debrief={debrief} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
