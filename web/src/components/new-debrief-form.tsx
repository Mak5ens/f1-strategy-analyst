"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
import { useActionState, useState } from "react";
import { type StartState, startDebrief } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { getMessages } from "@/lib/i18n";

const t = getMessages().home;

/** The request, in the analyst's words; examples fill the field. */
export function NewDebriefForm() {
  const [state, action, pending] = useActionState<StartState, FormData>(startDebrief, { error: false });
  const [request, setRequest] = useState("");
  return (
    <form action={action} className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-xl border bg-surface p-2 focus-within:border-primary/60 sm:flex-row">
        <input
          name="request"
          value={request}
          onChange={(event) => setRequest(event.target.value)}
          placeholder={t.placeholder}
          aria-label={t.placeholder}
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
          {t.error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">{t.examples}</span>
        {t.exampleRequests.map((example) => (
          <button
            key={example}
            type="button"
            disabled={pending}
            onClick={() => setRequest(example)}
            className="rounded-full border bg-band px-3 py-1.5 text-left text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
          >
            {example}
          </button>
        ))}
      </div>
    </form>
  );
}
