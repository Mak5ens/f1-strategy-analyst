"use client";

import { LoaderCircle } from "lucide-react";
import { useActionState } from "react";
import { type AnswerState, answerClarification } from "@/app/actions";
import type { Debrief } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().debrief;

/** The agent's question and its options, one click each. */
export function ClarificationStep({ debrief }: { debrief: Debrief }) {
  const [state, action, pending] = useActionState<AnswerState, FormData>(answerClarification.bind(null, debrief.id), {
    error: false,
  });
  const clarification = debrief.clarification;
  if (!clarification) return null;
  return (
    <section className="flex flex-col gap-6">
      <div>
        <h2 className="display text-2xl">{t.clarification.title}</h2>
        <p className="mt-2 text-muted-foreground">{t.clarification.lead}</p>
      </div>
      <p className="font-semibold text-lg">{clarification.question}</p>
      <form action={action} className="grid gap-3 sm:grid-cols-2">
        {clarification.options.map((option) => (
          <button
            key={option.label}
            type="submit"
            name="option"
            value={option.label}
            disabled={pending}
            className="flex items-center justify-between gap-3 rounded-xl border bg-surface px-5 py-4 text-left font-semibold transition hover:-translate-y-0.5 hover:border-primary/60 disabled:opacity-60"
          >
            {option.label}
            {pending ? <LoaderCircle className="size-4 animate-spin" /> : <span className="text-primary">→</span>}
          </button>
        ))}
      </form>
      {state.error && (
        <p role="alert" className="text-destructive text-sm">
          {t.error}
        </p>
      )}
    </section>
  );
}
