"use client";

import { cn } from "cn";
import { Check, LoaderCircle, Pencil, X } from "lucide-react";
import { type ReactNode, useActionState, useState } from "react";
import { type AnswerState, answerReview } from "@/app/actions";
import { Button } from "@/components/ui/button";
import type { Debrief, Decision, Point } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { PointStatus } from "./point-status";

const t = getMessages().debrief.review;

type Action = Decision["action"];
type Draft = { action: Action; text: string; reason: Decision["reason"] };

/** A decision is complete when a correction has its text, and a correction or a rejection its reason. */
export function complete(draft: Draft | undefined): boolean {
  if (!draft) return false;
  if (draft.action === "approve") return true;
  if (!draft.reason) return false;
  return draft.action === "reject" || draft.text.trim().length > 0;
}

/** Every point, with its evidence and three actions; the debrief is published once each is decided. */
export function ReviewStep({ debrief, evidence }: { debrief: Debrief; evidence: Record<string, ReactNode> }) {
  const [state, action, pending] = useActionState<AnswerState, FormData>(answerReview.bind(null, debrief.id), {
    error: false,
  });
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const set = (point: Point, change: Partial<Draft>) =>
    setDrafts((current) => {
      const previous = current[point.id] ?? { action: "approve", text: point.text, reason: null };
      return { ...current, [point.id]: { ...previous, ...change } };
    });
  const done = debrief.points.filter((point) => complete(drafts[point.id])).length;
  const decisions: Decision[] = debrief.points.flatMap((point) => {
    const draft = drafts[point.id];
    if (!draft) return [];
    return [
      {
        point: point.id,
        action: draft.action,
        text: draft.action === "correct" ? draft.text : null,
        reason: draft.action === "approve" ? null : draft.reason,
      },
    ];
  });
  return (
    <form action={action} className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="display text-2xl">{t.title}</h2>
          <p className="mt-2 max-w-2xl text-muted-foreground">{t.lead}</p>
        </div>
        <button
          type="button"
          className="rounded-full border px-3 py-1.5 text-sm hover:border-foreground/40"
          onClick={() =>
            setDrafts((current) => {
              const next = { ...current };
              for (const point of debrief.points)
                next[point.id] ??= { action: "approve", text: point.text, reason: null };
              return next;
            })
          }
        >
          {t.approveAll}
        </button>
      </div>
      <ol className="flex flex-col gap-4">
        {debrief.points.map((point, index) => {
          const draft = drafts[point.id];
          return (
            <li
              key={point.id}
              className={cn(
                "flex flex-col gap-4 rounded-xl border bg-surface p-5 transition-colors",
                point.status === "unverified" && "border-warning/60",
                draft?.action === "approve" && "border-success/50",
                draft?.action === "reject" && "border-destructive/50 opacity-80",
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <span className="display figures text-muted-foreground text-xl">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <PointStatus status={point.status} />
              </div>
              <p className={cn("text-base leading-relaxed", draft?.action === "reject" && "line-through")}>
                {point.text}
              </p>
              {point.problems.length > 0 && (
                <div className="rounded-lg border border-warning/40 bg-warning/5 px-3 py-2 text-sm">
                  <p className="font-semibold text-warning text-xs uppercase tracking-wide">{t.problems}</p>
                  <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                    {point.problems.map((problem) => (
                      <li key={problem}>{problem}</li>
                    ))}
                  </ul>
                </div>
              )}
              {evidence[point.id]}
              <fieldset className="flex flex-wrap gap-2">
                <legend className="sr-only">{`${t.title} ${index + 1}`}</legend>
                <Choice
                  name={`decision-${point.id}`}
                  active={draft?.action === "approve"}
                  tone="success"
                  onClick={() => set(point, { action: "approve" })}
                >
                  <Check className="size-4" /> {t.approve}
                </Choice>
                <Choice
                  name={`decision-${point.id}`}
                  active={draft?.action === "correct"}
                  tone="warning"
                  onClick={() => set(point, { action: "correct" })}
                >
                  <Pencil className="size-4" /> {t.correct}
                </Choice>
                <Choice
                  name={`decision-${point.id}`}
                  active={draft?.action === "reject"}
                  tone="destructive"
                  onClick={() => set(point, { action: "reject" })}
                >
                  <X className="size-4" /> {t.reject}
                </Choice>
              </fieldset>
              {draft && draft.action !== "approve" && (
                <div className="flex flex-col gap-3">
                  {draft.action === "correct" && (
                    <label className="flex flex-col gap-1.5 text-sm">
                      <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.correction}</span>
                      <textarea
                        value={draft.text}
                        onChange={(event) => set(point, { text: event.target.value })}
                        rows={3}
                        className="rounded-lg border bg-band px-3 py-2 text-base outline-none focus:border-primary/60"
                      />
                    </label>
                  )}
                  <label className="flex flex-col gap-1.5 text-sm sm:max-w-xs">
                    <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.reason}</span>
                    <select
                      value={draft.reason ?? ""}
                      onChange={(event) => set(point, { reason: (event.target.value || null) as Decision["reason"] })}
                      className="rounded-lg border bg-band px-3 py-2 outline-none focus:border-primary/60"
                    >
                      <option value="">{t.chooseReason}</option>
                      {Object.entries(t.reasons).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <input type="hidden" name="decisions" value={JSON.stringify(decisions)} />
      <div className="sticky bottom-4 flex flex-wrap items-center gap-4 rounded-xl border bg-band/95 p-4 backdrop-blur">
        <Button
          type="submit"
          size="lg"
          disabled={pending || done < debrief.points.length}
          className="h-12 px-6 font-semibold"
        >
          {pending && <LoaderCircle className="animate-spin" />}
          {pending ? t.submitting : t.submit}
        </Button>
        <span className="figures text-muted-foreground text-sm">{t.progress(done, debrief.points.length)}</span>
        {state.error && (
          <span role="alert" className="text-destructive text-sm">
            {getMessages().debrief.error}
          </span>
        )}
      </div>
    </form>
  );
}

const tones = {
  success: "has-checked:border-success has-checked:bg-success/15 has-checked:text-success",
  warning: "has-checked:border-warning has-checked:bg-warning/15 has-checked:text-warning",
  destructive: "has-checked:border-destructive has-checked:bg-destructive/15 has-checked:text-destructive",
};

function Choice({
  name,
  active,
  tone,
  onClick,
  children,
}: {
  name: string;
  active: boolean;
  tone: keyof typeof tones;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-1.5 rounded-full border px-4 py-1.5 font-semibold text-sm transition-colors hover:border-foreground/40",
        "has-focus-visible:ring-2 has-focus-visible:ring-ring",
        tones[tone],
      )}
    >
      <input type="radio" name={name} checked={active} onChange={onClick} className="sr-only" />
      {children}
    </label>
  );
}
