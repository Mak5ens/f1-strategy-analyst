"use client";

import { cn } from "cn";
import { LoaderCircle } from "lucide-react";
import { useActionState, useState } from "react";
import { type AnswerState, answerPlan } from "@/app/actions";
import { teamStyle } from "@/components/race/driver-cell";
import { Button } from "@/components/ui/button";
import type { Analysis, Debrief } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().debrief.plan;

type Group = { key: string; title: string; colour: string | null; analyses: Analysis[] };

/** The analyses by driver, the race-wide ones first; a driver followed gets their team's colour. */
export function planGroups(debrief: Debrief): Group[] {
  const drivers = new Map(debrief.subject.focus.map((driver) => [driver.code, driver]));
  const groups = new Map<string, Group>();
  for (const analysis of debrief.plan) {
    const code = typeof analysis.arguments.driver === "string" ? analysis.arguments.driver : null;
    const key = code ?? "race";
    if (!groups.has(key)) {
      const driver = code ? drivers.get(code) : undefined;
      groups.set(key, {
        key,
        title: code ? (driver?.name ?? code) : t.race,
        colour: code ? (driver?.colour ?? null) : debrief.subject.colour,
        analyses: [],
      });
    }
    groups.get(key)?.analyses.push(analysis);
  }
  return [...groups.values()].toSorted((a, b) => Number(a.key !== "race") - Number(b.key !== "race"));
}

/** The plan as cards to tick, grouped by driver: what is ticked runs. */
export function PlanStep({ debrief }: { debrief: Debrief }) {
  const [state, action, pending] = useActionState<AnswerState, FormData>(answerPlan.bind(null, debrief.id), {
    error: false,
  });
  const [selected, setSelected] = useState(
    () => new Set(debrief.plan.filter((analysis) => analysis.selected).map((analysis) => analysis.id)),
  );
  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <form action={action} className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="display text-2xl">{getMessages().debrief.plan.title}</h2>
          <p className="mt-2 max-w-2xl text-muted-foreground">{t.lead}</p>
        </div>
        <div className="flex gap-2 text-sm">
          <button
            type="button"
            className="rounded-full border px-3 py-1.5 hover:border-foreground/40"
            onClick={() => setSelected(new Set(debrief.plan.map((analysis) => analysis.id)))}
          >
            {t.all}
          </button>
          <button
            type="button"
            className="rounded-full border px-3 py-1.5 hover:border-foreground/40"
            onClick={() => setSelected(new Set())}
          >
            {t.none}
          </button>
        </div>
      </div>
      {planGroups(debrief).map((group) => (
        <fieldset key={group.key} className="flex flex-col gap-3" style={teamStyle(group.colour)}>
          <legend className="mb-3 flex items-center gap-2 font-semibold">
            <span className="slash" aria-hidden />
            {group.title}
          </legend>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.analyses.map((analysis) => {
              const checked = selected.has(analysis.id);
              return (
                <label
                  key={analysis.id}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-xl border bg-surface p-4 transition",
                    checked
                      ? "border-[color-mix(in_oklab,var(--team)_60%,transparent)] bg-[linear-gradient(115deg,color-mix(in_oklab,var(--team)_18%,transparent),transparent_70%)]"
                      : "opacity-60 hover:opacity-90",
                  )}
                >
                  <input
                    type="checkbox"
                    name="analysis"
                    value={analysis.id}
                    checked={checked}
                    onChange={() => toggle(analysis.id)}
                    className="mt-0.5 size-4 accent-primary"
                  />
                  <span className="text-sm">{analysis.label}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}
      <div className="sticky bottom-4 flex flex-wrap items-center gap-4 rounded-xl border bg-band/95 p-4 backdrop-blur">
        <Button type="submit" size="lg" disabled={pending || selected.size === 0} className="h-12 px-6 font-semibold">
          {pending && <LoaderCircle className="animate-spin" />}
          {t.submit(selected.size)}
        </Button>
        {pending && <span className="text-muted-foreground text-sm">{t.submitting}</span>}
        {state.error && (
          <span role="alert" className="text-destructive text-sm">
            {getMessages().debrief.error}
          </span>
        )}
      </div>
    </form>
  );
}
