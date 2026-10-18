import { cn } from "cn";
import Link from "next/link";
import type { FreeAnswer } from "@/lib/api/client";
import { formatAgo } from "@/lib/format";
import { getMessages } from "@/lib/i18n";

const t = getMessages().answer;

/** The free questions asked last, each opening its answer on the home page; a debrief opens its request. */
export function RecentQuestions({ questions, current }: { questions: FreeAnswer[]; current?: number }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {questions.map((question) => (
        <li key={question.id}>
          <Link
            href={question.debrief ? `/debriefs/${question.debrief}` : `/?question=${question.id}#reponse`}
            className={cn(
              "flex h-full flex-col gap-2 rounded-xl border bg-surface px-4 py-3 transition-colors hover:border-primary/50",
              question.id === current && "border-primary/60",
            )}
          >
            <span className="flex items-center justify-between gap-2 text-muted-foreground text-xs">
              <span className="font-semibold uppercase tracking-wide">
                {question.route ? t.routes[question.route] : t.asked}
                {question.status !== "answered" && question.status !== "debrief" && ` · ${t.short[question.status]}`}
              </span>
              {question.asked_at && <time dateTime={question.asked_at}>{formatAgo(question.asked_at)}</time>}
            </span>
            <span className="line-clamp-2 font-medium">{question.question}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
