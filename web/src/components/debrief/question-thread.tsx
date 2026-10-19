import { cn } from "cn";
import { FiguresText } from "@/components/figures-text";
import { SectionTitle } from "@/components/section-title";
import type { Debrief, QuestionReply, RaceLaps } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { PointEvidence } from "./point-evidence";
import { QuestionAsk } from "./question-ask";

const t = getMessages().debrief.questions;

/** Questions to start from: the analyses the debrief's points rest on, the race's classification aside. */
export function questionSuggestions(debrief: Debrief, count = 3): string[] {
  const cited = new Set(debrief.points.flatMap((point) => point.facts));
  return debrief.facts
    .filter((fact) => fact.ok && cited.has(fact.id) && fact.id !== "result")
    .slice(0, count)
    .map((fact) => t.detail(fact.label));
}

/** The questions asked under a published debrief, each with its answer, or why it is not shown; then a new one. */
export function QuestionThread({
  debrief,
  replies,
  laps = null,
}: {
  debrief: Debrief;
  replies: QuestionReply[];
  laps?: RaceLaps | null;
}) {
  return (
    <section id="questions" className="scroll-mt-24">
      <SectionTitle>{t.title}</SectionTitle>
      <p className="mb-6 max-w-3xl text-muted-foreground">{t.lead}</p>
      <ol className="mb-6 flex flex-col gap-4">
        {replies.map((reply) => (
          <li key={reply.id} id={`question-${reply.id}`} className="flex scroll-mt-24 flex-col gap-3">
            <p className="ml-auto max-w-2xl rounded-xl rounded-br-sm bg-surface-raised px-4 py-3 font-semibold">
              {reply.question}
            </p>
            <div
              className={cn(
                "max-w-3xl rounded-xl rounded-bl-sm border bg-surface px-5 py-4",
                reply.status !== "answered" && "border-dashed",
              )}
            >
              {reply.status === "answered" ? (
                <ul className="flex flex-col gap-3">
                  {reply.points.map((point) => (
                    <li key={point.id} className="flex flex-col gap-2">
                      <p className="text-foreground/85 leading-relaxed">
                        <FiguresText text={point.text} />
                      </p>
                      <PointEvidence point={point} evidence={reply} laps={laps} />
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="flex flex-col gap-1 text-sm">
                  <p className={cn("font-semibold", reply.status === "refused" ? "text-foreground" : "text-warning")}>
                    {t[reply.status]}
                  </p>
                  {reply.reason &&
                    (reply.status === "refused" ? (
                      <p className="text-muted-foreground">{reply.reason}</p>
                    ) : (
                      <details className="text-muted-foreground text-xs">
                        <summary className="cursor-pointer">{t.checked}</summary>
                        <p className="mt-1">{reply.reason}</p>
                      </details>
                    ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
      {!replies.length && <p className="mb-6 text-muted-foreground text-sm">{t.empty}</p>}
      <QuestionAsk id={debrief.id} suggestions={questionSuggestions(debrief)} />
    </section>
  );
}
