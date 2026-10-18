import { cn } from "cn";
import { BookOpen, Calculator, CircleHelp } from "lucide-react";
import Link from "next/link";
import { FiguresText } from "@/components/figures-text";
import type { FreeAnswer as Answer } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { ChoiceForm } from "./choice-form";

const t = getMessages().answer;

/**
 * The answer to a free question, on the home page: the claims of the rules with their FIA passages, or the points
 * computed on a race's data with the analyses they come from; an abstention or a withheld answer says why; a
 * question to make precise lists what the analyst may choose.
 */
export function FreeAnswer({ answer }: { answer: Answer }) {
  const rules = answer.route === "rules";
  return (
    <article id="reponse" className="flex scroll-mt-24 flex-col gap-3" aria-label={answer.question}>
      <p className="ml-auto max-w-2xl rounded-xl rounded-br-sm bg-surface-raised px-4 py-3 font-semibold">
        {answer.question}
      </p>
      <div
        className={cn(
          "flex flex-col gap-4 rounded-xl rounded-bl-sm border bg-surface px-5 py-4",
          answer.status !== "answered" && "border-dashed",
        )}
      >
        <p className="flex items-center gap-2 font-semibold text-muted-foreground text-xs uppercase tracking-wide">
          {answer.status === "asked" ? (
            <CircleHelp className="size-4 text-primary" />
          ) : rules ? (
            <BookOpen className="size-4 text-primary" />
          ) : (
            <Calculator className="size-4 text-primary" />
          )}
          {answer.status === "asked" ? t.asked : rules ? t.routed : t.computed}
        </p>

        {answer.status === "answered" && (
          <ul className="flex flex-col gap-3">
            {answer.points.map((point) => (
              <li key={point.text} className="text-foreground/90 leading-relaxed">
                <FiguresText text={point.text} />
                {point.sources.length > 0 && (
                  <span className="ml-1.5 text-muted-foreground text-xs">[{point.sources.join(", ")}]</span>
                )}
              </li>
            ))}
          </ul>
        )}

        {answer.status === "asked" && (
          <div className="flex flex-col gap-3">
            <p>{answer.reason}</p>
            <ChoiceForm question={answer.question} choices={answer.choices} />
          </div>
        )}

        {answer.status !== "answered" && answer.status !== "asked" && (
          <div className="flex flex-col gap-1 text-sm">
            <p className={cn("font-semibold", answer.status === "abstained" ? "text-foreground" : "text-warning")}>
              {t[answer.status]}
            </p>
            {answer.reason &&
              (answer.status === "withheld" || answer.status === "stopped" ? (
                <details className="text-muted-foreground text-xs">
                  <summary className="cursor-pointer">{t.checked}</summary>
                  <p className="mt-1">{answer.reason}</p>
                </details>
              ) : (
                <p className="text-muted-foreground">{answer.reason}</p>
              ))}
          </div>
        )}

        {answer.notes.map((note) => (
          <p key={note} className="text-muted-foreground text-sm italic">
            {note}
          </p>
        ))}

        {answer.facts.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.figures}</span>
            {answer.facts.map((fact) => (
              <span key={fact.id} className="rounded-full bg-band px-2.5 py-1 text-xs">
                {fact.label}
              </span>
            ))}
          </div>
        )}

        {answer.sources.length > 0 && (
          <div className="flex flex-col gap-2 text-sm">
            <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.sources}</span>
            {answer.sources.map((source) => (
              <details key={source.id} className="rounded-lg bg-band px-3 py-2">
                <summary className="cursor-pointer font-medium text-xs marker:text-primary">
                  {source.id} · {source.label}
                </summary>
                {source.text && (
                  <p className="mt-2 whitespace-pre-line text-muted-foreground text-xs leading-relaxed">
                    {source.text}
                  </p>
                )}
                {source.url && (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-block font-semibold text-primary text-xs hover:underline"
                  >
                    {t.openSource} ↗
                  </a>
                )}
              </details>
            ))}
          </div>
        )}

        {answer.race && (
          <Link
            href={`/grand-prix/${answer.race.season}/${answer.race.round}`}
            className="self-start font-semibold text-sm hover:text-primary"
          >
            {t.seeRace(`${answer.race.grand_prix} ${answer.race.season}`)} →
          </Link>
        )}
      </div>
    </article>
  );
}
