import { StrategyChart } from "@/components/race/strategy-chart";
import { SectionTitle } from "@/components/section-title";
import type { Debrief, Race } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { PointEvidence } from "./point-evidence";
import { PointStatus } from "./point-status";

const t = getMessages().debrief.published;

/** The drivers a debrief is about: those it follows, or the team's, or none for the whole race. */
function followed(debrief: Debrief, race: Race): Set<string> {
  const codes = new Set(debrief.subject.focus.map((driver) => driver.code));
  if (!codes.size)
    for (const strategy of race.strategies)
      if (strategy.driver.team && debrief.subject.teams.includes(strategy.driver.team)) codes.add(strategy.driver.code);
  return codes;
}

/** A published debrief: its points with their figures and sources, the strategy of the drivers it follows, the review. */
export function PublishedDebrief({ debrief, race }: { debrief: Debrief; race: Race | null }) {
  const codes = race ? followed(debrief, race) : new Set<string>();
  const strategies = race?.strategies.filter((strategy) => codes.has(strategy.driver.code)) ?? [];
  const count = (action: string) => debrief.decisions.filter((decision) => decision.action === action).length;
  return (
    <div className="flex flex-col gap-14">
      <section>
        <SectionTitle>{t.points}</SectionTitle>
        <ol className="flex flex-col gap-4">
          {debrief.points.map((point, index) => (
            <li key={point.id} className="flex flex-col gap-4 rounded-xl border bg-surface p-5">
              <div className="flex items-start justify-between gap-4">
                <span className="display figures text-muted-foreground text-xl">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <PointStatus status={point.status} />
              </div>
              <p className="text-base leading-relaxed">{point.text}</p>
              <PointEvidence point={point} debrief={debrief} />
            </li>
          ))}
        </ol>
        <p className="mt-4 text-muted-foreground text-sm">{t.method}</p>
      </section>
      {race && strategies.length > 0 && (
        <section>
          <SectionTitle>{t.strategy}</SectionTitle>
          <StrategyChart race={{ ...race, strategies }} />
        </section>
      )}
      {debrief.decisions.length > 0 && (
        <section>
          <SectionTitle href={`/journal?debrief=${debrief.id}`} link={getMessages().journal.title}>
            {t.decisions}
          </SectionTitle>
          <p className="text-muted-foreground">{t.summary(count("approve"), count("correct"), count("reject"))}</p>
        </section>
      )}
    </div>
  );
}
