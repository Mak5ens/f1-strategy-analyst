import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { AutoRefresh } from "@/components/debrief/auto-refresh";
import { ClarificationStep } from "@/components/debrief/clarification-step";
import { PlanStep } from "@/components/debrief/plan-step";
import { PointEvidence } from "@/components/debrief/point-evidence";
import { PublishedDebrief } from "@/components/debrief/published-debrief";
import { ReviewStep } from "@/components/debrief/review-step";
import { teamStyle } from "@/components/race/driver-cell";
import { debriefTitle, subjectFor, subjectTitle } from "@/components/subject-line";
import { type Debrief, fetchDebrief, fetchQuestions, fetchRace, fetchRaceLaps } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

type Params = Promise<{ id: string }>;

const t = getMessages().debrief;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const debrief = await fetchDebrief((await params).id);
  const title = debrief ? debriefTitle(debrief) : t.missing;
  return { title: `${title} · ${getMessages().metadata.title}` };
}

/** A request where it stands: the agent's question, its plan, its points to review, or the debrief published. */
export default async function DebriefPage({ params }: { params: Params }) {
  await connection();
  const debrief = await fetchDebrief((await params).id);
  if (!debrief) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-24">
        <p className="text-lg text-muted-foreground">{t.missing}</p>
      </main>
    );
  }
  const { subject } = debrief;
  const published = debrief.status === "published";
  const raced = subject.season && subject.round ? ([subject.season, subject.round] as const) : null;
  const [race, replies, lapsFound] = await Promise.all([
    published && raced ? fetchRace(...raced) : null,
    published ? fetchQuestions(debrief.id) : null,
    // The charts of the points' numbers (LAB-189): in the review, to check them, and once published.
    (published || debrief.waiting === "review") && raced ? fetchRaceLaps(...raced) : null,
  ]);
  const laps = lapsFound && lapsFound !== "missing" ? lapsFound : null;
  return (
    <main>
      <DebriefHeader debrief={debrief} />
      <div className="mx-auto max-w-6xl px-4 py-10">
        {debrief.status === "running" && (
          <section className="rounded-xl border bg-surface p-6">
            <AutoRefresh />
            <h2 className="display text-2xl">{t.running.title}</h2>
            <p className="mt-2 text-muted-foreground">{t.running.lead}</p>
          </section>
        )}
        {debrief.status === "stopped" && (
          <section className="rounded-xl border border-destructive/50 bg-surface p-6">
            <h2 className="display text-2xl">{t.stopped.title}</h2>
            <p className="mt-2 text-muted-foreground">
              {t.stopped.lead} {debrief.stop_reason}
            </p>
          </section>
        )}
        {debrief.waiting === "clarification" && <ClarificationStep debrief={debrief} />}
        {debrief.waiting === "plan" && <PlanStep debrief={debrief} />}
        {debrief.waiting === "review" && (
          <ReviewStep
            debrief={debrief}
            evidence={Object.fromEntries(
              debrief.points.map((point) => [
                point.id,
                <PointEvidence key={point.id} point={point} evidence={debrief} laps={laps} />,
              ]),
            )}
          />
        )}
        {debrief.status === "published" && (
          <PublishedDebrief
            debrief={debrief}
            race={race && race !== "missing" ? race : null}
            laps={laps}
            replies={replies ?? []}
          />
        )}
      </div>
    </main>
  );
}

/** The band on top, in the colour of the team followed: the race, who it is for, the request as typed. */
function DebriefHeader({ debrief }: { debrief: Debrief }) {
  const { subject } = debrief;
  const stop = debrief.waiting ? getMessages().stops[debrief.waiting].label : t.status[debrief.status];
  return (
    <section className="relative overflow-hidden border-b bg-band" style={teamStyle(subject.colour)}>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(110deg,color-mix(in_oklab,var(--team)_30%,transparent)_0%,transparent_50%)]"
      />
      {subject.round != null && (
        <span
          aria-hidden
          className="display figures pointer-events-none absolute -right-4 -bottom-10 text-[10rem] text-watermark italic sm:text-[15rem]"
        >
          {String(subject.round).padStart(2, "0")}
        </span>
      )}
      <div className="relative mx-auto flex max-w-6xl flex-col gap-4 px-4 pt-12 pb-10">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-full bg-primary px-3 py-1 font-semibold text-primary-foreground text-xs uppercase tracking-wide">
            {stop}
          </span>
        </div>
        {subject.question && (
          <p className="font-semibold text-muted-foreground uppercase tracking-wide">{subjectTitle(subject)}</p>
        )}
        <h1
          className={subject.question ? "display text-2xl leading-tight sm:text-4xl" : "display text-3xl sm:text-5xl"}
        >
          {debriefTitle(debrief)}
        </h1>
        {subject.grand_prix && (
          <p className="flex items-center gap-2 font-semibold text-lg">
            <span className="slash" aria-hidden />
            {subjectFor(subject)}
          </p>
        )}
        {!subject.question && (
          <p className="max-w-3xl text-muted-foreground">
            <span className="text-xs uppercase tracking-wide">{t.request} · </span>« {debrief.request} »
          </p>
        )}
        {subject.season && subject.round && (
          <Link
            href={`/grand-prix/${subject.season}/${subject.round}`}
            className="w-fit font-semibold text-primary-text text-sm"
          >
            {t.seeRace} →
          </Link>
        )}
      </div>
    </section>
  );
}
