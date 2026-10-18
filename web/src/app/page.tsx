import { connection } from "next/server";
import { AskForm } from "@/components/ask/ask-form";
import { FreeAnswer } from "@/components/ask/free-answer";
import { RecentQuestions } from "@/components/ask/recent-questions";
import { DebriefCard } from "@/components/debrief-card";
import { PublishedTable } from "@/components/published-table";
import { CalendarGrid } from "@/components/race/calendar-grid";
import { LatestRace } from "@/components/race/latest-race";
import { RaceCard } from "@/components/race/race-card";
import { SeasonPicker } from "@/components/race/season-picker";
import { SectionTitle } from "@/components/section-title";
import {
  fetchDebriefs,
  fetchFeatured,
  fetchFreeQuestion,
  fetchFreeQuestions,
  fetchRaces,
  fetchSeasons,
} from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

/**
 * The race is the entry point: the last race and a few others first, then the season's calendar, a race two clicks
 * away at most. A free question can be typed at the top (LAB-206), its answer shown under it (`?question=`); what
 * waits for the analyst follows.
 */
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ saison?: string; question?: string }>;
}) {
  await connection();
  const params = await searchParams;
  const questionId = Number(params.question) || undefined;
  const [featured, seasons, waiting, published, recent, answer] = await Promise.all([
    fetchFeatured(),
    fetchSeasons(),
    fetchDebriefs({ status: "waiting" }),
    fetchDebriefs({ status: "published" }),
    fetchFreeQuestions(),
    questionId ? fetchFreeQuestion(questionId) : null,
  ]);
  const asked = Number(params.saison);
  const season = seasons?.includes(asked) ? asked : seasons?.[0];
  const races = season ? await fetchRaces(season) : null;
  const [latest, ...others] = featured ?? [];
  const t = getMessages().home;
  return (
    <main>
      <section className="relative overflow-hidden border-b bg-band">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-0 w-1/2 bg-[repeating-linear-gradient(115deg,transparent_0_46px,rgb(255_255_255/0.025)_46px_92px)] [mask-image:linear-gradient(to_left,black,transparent)]"
        />
        <div className="relative mx-auto flex max-w-6xl flex-col gap-6 px-4 py-12 sm:py-16">
          <p className="flex items-center gap-2 font-semibold text-primary text-sm uppercase tracking-wider">
            <span className="slash" aria-hidden />
            {t.eyebrow}
          </p>
          <h1 className="display max-w-4xl text-4xl sm:text-6xl">{t.title}</h1>
          <p className="max-w-2xl text-lg text-muted-foreground">{t.lead}</p>
          <div className="flex max-w-3xl flex-col gap-6">
            <AskForm />
            {answer && <FreeAnswer answer={answer} />}
          </div>
        </div>
      </section>

      {recent && recent.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 pt-14">
          <SectionTitle>{t.recentTitle}</SectionTitle>
          <RecentQuestions questions={recent} current={answer?.id} />
        </section>
      )}

      {latest && (
        <section className="mx-auto max-w-6xl px-4 pt-14">
          <SectionTitle href={`/grand-prix?saison=${latest.season}`} link={t.fullCalendar}>
            {t.latestTitle}
          </SectionTitle>
          <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <LatestRace race={latest} />
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
              {others.slice(0, 2).map((race) => (
                <RaceCard key={`${race.season}-${race.round}`} race={race} />
              ))}
            </div>
          </div>
        </section>
      )}

      {waiting && waiting.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 pt-16">
          <SectionTitle href="/en-attente" link={t.seeAll}>
            {t.waitingTitle}
          </SectionTitle>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {waiting.slice(0, 3).map((debrief) => (
              <DebriefCard key={debrief.id} debrief={debrief} />
            ))}
          </div>
        </section>
      )}

      {season && races && (
        <section className="mx-auto max-w-6xl px-4 pt-16">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <h2 className="display flex items-center gap-3 text-2xl sm:text-3xl">
              <span className="slash" aria-hidden />
              {t.calendarTitle(season)}
            </h2>
            {seasons && (
              <SeasonPicker seasons={seasons} current={season} href={(year) => `/?saison=${year}#calendrier`} />
            )}
          </div>
          <div id="calendrier" className="scroll-mt-24">
            <CalendarGrid races={races} />
          </div>
        </section>
      )}

      <section className="mx-auto max-w-6xl px-4 pt-16">
        <SectionTitle href="/debriefs" link={t.seeAll}>
          {t.publishedTitle}
        </SectionTitle>
        {published?.length ? (
          <PublishedTable debriefs={published.slice(0, 6)} />
        ) : (
          <p className="text-muted-foreground">{t.publishedEmpty}</p>
        )}
      </section>
    </main>
  );
}
