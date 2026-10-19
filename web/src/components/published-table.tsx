import Link from "next/link";
import type { CSSProperties } from "react";
import { subjectFor, subjectTitle } from "@/components/subject-line";
import type { DebriefSummary } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { getMessages } from "@/lib/i18n";

const t = getMessages().table;

/** Published debriefs on a black panel: small upper-case headers, thin rules, a dot of the team's colour. */
export function PublishedTable({ debriefs }: { debriefs: DebriefSummary[] }) {
  return (
    <div className="overflow-x-auto rounded-xl bg-band px-2 sm:px-6">
      <table className="w-full min-w-[36rem] text-left text-sm">
        <thead className="text-muted-foreground text-xs uppercase tracking-wide">
          <tr className="border-b">
            <th className="py-4 pr-4 font-semibold">{t.grandPrix}</th>
            <th className="py-4 pr-4 font-semibold">{t.season}</th>
            <th className="py-4 pr-4 font-semibold">{t.subject}</th>
            <th className="py-4 text-right font-semibold">{t.published}</th>
          </tr>
        </thead>
        <tbody>
          {debriefs.map((debrief) => (
            <tr key={debrief.id} className="border-b transition-colors last:border-0 hover:bg-hover">
              <td className="py-4 pr-4 font-semibold">
                <Link href={`/debriefs/${debrief.id}`} className="hover:text-primary-text">
                  {debrief.subject.question
                    ? debrief.request
                    : (debrief.subject.grand_prix ?? subjectTitle(debrief.subject))}
                </Link>
              </td>
              <td className="figures py-4 pr-4">{debrief.subject.season}</td>
              <td className="py-4 pr-4">
                <span
                  className="flex items-center gap-2"
                  style={{ "--team": debrief.subject.colour ?? "var(--muted-foreground)" } as CSSProperties}
                >
                  <span className="size-2.5 rounded-full bg-[var(--team)]" aria-hidden />
                  {subjectFor(debrief.subject)}
                </span>
              </td>
              <td className="figures py-4 text-right text-muted-foreground">{formatDate(debrief.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
