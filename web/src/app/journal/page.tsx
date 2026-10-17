import { cn } from "cn";
import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { FilterPills } from "@/components/filter-pills";
import { PageHeader } from "@/components/page-header";
import { subjectFor, subjectTitle } from "@/components/subject-line";
import { type Decision, fetchJournal } from "@/lib/api/client";
import { formatAgo } from "@/lib/format";
import { getMessages } from "@/lib/i18n";

const t = getMessages();

export const metadata: Metadata = { title: `${t.journal.title} · ${t.metadata.title}` };

const actions: Decision["action"][] = ["reject", "correct", "approve"];
const tones: Record<string, string> = {
  approve: "bg-success/15 text-success",
  correct: "bg-warning/15 text-warning",
  reject: "bg-destructive/15 text-destructive",
};

/** Every review decision with the agent's text, `?action=reject` or `?debrief=<id>` to narrow it. */
export default async function Journal({
  searchParams,
}: {
  searchParams: Promise<{ action?: string; debrief?: string }>;
}) {
  await connection();
  const query = await searchParams;
  const action = actions.find((name) => name === query.action);
  const entries = await fetchJournal({ debrief: query.debrief, action: action ? [action] : undefined });
  const scope = query.debrief ? `debrief=${query.debrief}&` : "";
  const now = new Date();
  return (
    <main>
      <PageHeader title={t.journal.title} lead={t.journal.lead}>
        <FilterPills
          pills={[
            { label: t.journal.all, href: `/journal${scope ? `?${scope.slice(0, -1)}` : ""}`, active: !action },
            ...actions.map((name) => ({
              label: t.journal.actions[name] ?? name,
              href: `/journal?${scope}action=${name}`,
              active: action === name,
            })),
          ]}
        />
      </PageHeader>
      <section className="mx-auto max-w-6xl px-4 py-12">
        {entries?.length ? (
          <ol className="flex flex-col gap-3">
            {entries.map((entry) => (
              <li key={entry.id} className="flex flex-col gap-3 rounded-xl border bg-surface p-5">
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span
                    className={cn(
                      "rounded-full px-2.5 py-1 font-semibold text-xs uppercase tracking-wide",
                      tones[entry.action],
                    )}
                  >
                    {t.journal.actions[entry.action]}
                    {entry.reason && ` · ${t.debrief.review.reasons[entry.reason]}`}
                  </span>
                  <Link href={`/debriefs/${entry.debrief}`} className="font-semibold hover:text-primary">
                    {subjectTitle(entry.subject)} · {subjectFor(entry.subject)} · {entry.point}
                  </Link>
                  <span className="ml-auto text-muted-foreground">
                    {t.journal.by(entry.decided_by, formatAgo(entry.decided_at, now))}
                  </span>
                </div>
                <div className={cn("grid gap-3", entry.text_after && "md:grid-cols-2")}>
                  <div>
                    <p className="text-muted-foreground text-xs uppercase tracking-wide">{t.journal.before}</p>
                    <p className={cn("mt-1", entry.action === "reject" && "line-through opacity-70")}>
                      {entry.text_before}
                    </p>
                  </div>
                  {entry.text_after && (
                    <div>
                      <p className="text-muted-foreground text-xs uppercase tracking-wide">{t.journal.after}</p>
                      <p className="mt-1">{entry.text_after}</p>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-muted-foreground">{t.journal.empty}</p>
        )}
      </section>
    </main>
  );
}
