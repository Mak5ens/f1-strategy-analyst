"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
import { useActionState, useState } from "react";
import { type StartState, startDebrief } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { getMessages } from "@/lib/i18n";

const t = getMessages().race.question;

/** A question on this race, with the questions the race raises to start from: the race goes with it, never asked. */
export function QuestionForm({ season, round, suggestions }: { season: number; round: number; suggestions: string[] }) {
  const [state, action, pending] = useActionState<StartState, FormData>(startDebrief, { error: false });
  const [question, setQuestion] = useState("");
  return (
    <form action={action} className="flex flex-col gap-4 rounded-xl border bg-surface p-5 sm:p-6">
      <div>
        <h2 className="display text-xl sm:text-2xl">{t.title}</h2>
        <p className="mt-2 max-w-3xl text-muted-foreground text-sm">{t.lead}</p>
      </div>
      <input type="hidden" name="season" value={season} />
      <input type="hidden" name="round" value={round} />
      <input type="hidden" name="question" value="1" />
      <div className="flex flex-col gap-3 rounded-xl border bg-band p-2 focus-within:border-primary/60 sm:flex-row">
        <input
          name="request"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={t.placeholder}
          aria-label={t.title}
          required
          minLength={3}
          maxLength={500}
          disabled={pending}
          className="min-w-0 flex-1 bg-transparent px-3 py-3 text-base outline-none placeholder:text-muted-foreground/70"
        />
        <Button type="submit" size="lg" disabled={pending} className="h-12 rounded-lg px-6 font-semibold">
          {pending ? <LoaderCircle className="animate-spin" /> : <ArrowRight />}
          {pending ? t.submitting : t.submit}
        </Button>
      </div>
      {state.error && (
        <p role="alert" className="text-destructive text-sm">
          {getMessages().home.error}
        </p>
      )}
      {suggestions.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">{t.suggestions}</span>
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={pending}
              onClick={() => setQuestion(suggestion)}
              className="rounded-full border bg-band px-3 py-1.5 text-left text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
    </form>
  );
}
