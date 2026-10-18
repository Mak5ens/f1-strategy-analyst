import { cn } from "cn";
import { FiguresText } from "@/components/figures-text";
import { StrategyChart } from "@/components/race/strategy-chart";
import { SectionTitle } from "@/components/section-title";
import type { Debrief, QuestionReply, Race } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { PointEvidence } from "./point-evidence";
import { momentNumbers, PointHeader, partStyle } from "./point-header";
import { QuestionThread } from "./question-thread";
import { DebriefPart, timelinePlaces } from "./timeline";

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
export function PublishedDebrief({
  debrief,
  race,
  replies,
}: {
  debrief: Debrief;
  race: Race | null;
  replies: QuestionReply[];
}) {
  const codes = race ? followed(debrief, race) : new Set<string>();
  const strategies = race?.strategies.filter((strategy) => codes.has(strategy.driver.code)) ?? [];
  const numbers = momentNumbers(debrief.points);
  const places = timelinePlaces(debrief.points);
  const count = (action: string) => debrief.decisions.filter((decision) => decision.action === action).length;
  return (
    <div className="flex flex-col gap-14">
      <section>
        <SectionTitle>{t.points}</SectionTitle>
        <ol className="flex flex-col gap-4">
          {debrief.points.map((point) => (
            <DebriefPart
              key={point.id}
              point={point}
              place={places.get(point.id)}
              className={cn("flex flex-col gap-4 rounded-xl border bg-surface p-5", partStyle(point))}
            >
              <PointHeader point={point} number={numbers.get(point.id)} />
              <p
                className={cn(
                  "text-foreground/85 leading-relaxed",
                  point.kind === "summary" ? "text-lg text-foreground" : "text-base",
                )}
              >
                <FiguresText text={point.text} />
              </p>
              <PointEvidence point={point} evidence={debrief} />
            </DebriefPart>
          ))}
        </ol>
        <p className="mt-4 text-muted-foreground text-sm">{t.method}</p>
      </section>
      <QuestionThread debrief={debrief} replies={replies} />
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
