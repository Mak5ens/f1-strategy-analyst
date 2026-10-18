"use client";

import { LoaderCircle } from "lucide-react";
import { useActionState } from "react";
import { type AnswerState, askFree } from "@/app/actions";
import type { Choice } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().home;

/** What the analyst may choose for a question: each choice sends the question again with it. */
export function ChoiceForm({ question, choices }: { question: string; choices: Choice[] }) {
  const [state, action, pending] = useActionState<AnswerState, FormData>(askFree, { error: false });
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {choices.map((choice) => (
          <form key={choice.label} action={action}>
            <input type="hidden" name="question" value={question} />
            <input type="hidden" name="route" value={choice.route} />
            {choice.season && choice.round && (
              <>
                <input type="hidden" name="season" value={choice.season} />
                <input type="hidden" name="round" value={choice.round} />
              </>
            )}
            <button
              type="submit"
              disabled={pending}
              className="rounded-full border bg-band px-3.5 py-1.5 font-medium text-sm transition-colors hover:border-primary/60 disabled:opacity-60"
            >
              {choice.label}
            </button>
          </form>
        ))}
        {pending && <LoaderCircle aria-label={t.submitting} className="size-5 animate-spin" />}
      </div>
      {state.error && (
        <p role="alert" className="text-destructive text-sm">
          {t.error}
        </p>
      )}
    </div>
  );
}
