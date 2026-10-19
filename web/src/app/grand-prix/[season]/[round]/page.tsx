import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { DebriefCard } from "@/components/debrief-card";
import { PublishedTable } from "@/components/published-table";
import { GridTable } from "@/components/race/grid-table";
import { PreparedDebriefs } from "@/components/race/prepared-debriefs";
import { QuestionForm } from "@/components/race/question-form";
import { RaceCharts } from "@/components/race/race-charts";
import { RaceEvents } from "@/components/race/race-events";
import { RaceHero } from "@/components/race/race-hero";
import { RaceTabs } from "@/components/race/race-tabs";
import { ResultTable } from "@/components/race/result-table";
import { StandingsTables } from "@/components/race/standings-tables";
import { StrategyChart } from "@/components/race/strategy-chart";
import { SectionTitle } from "@/components/section-title";
import { fetchDebriefs, fetchRace, fetchRaceLaps } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { raceSuggestions } from "@/lib/suggestions";

type Params = Promise<{ season: string; round: string }>;

const t = getMessages().race;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { season, round } = await params;
  const race = await fetchRace(Number(season), Number(round));
  const name = race && race !== "missing" ? `${race.summary.grand_prix} ${season}` : t.missing.title;
  return { title: `${name} · ${getMessages().metadata.title}` };
}

/** A Grand Prix: what happened, read from the data without a model, then the debriefs of the race. */
export default async function GrandPrixPage({ params }: { params: Params }) {
  await connection();
  const { season, round } = await params;
  const [race, debriefs, laps] = await Promise.all([
    fetchRace(Number(season), Number(round)),
    fetchDebriefs({ season: Number(season), round: Number(round) }),
    fetchRaceLaps(Number(season), Number(round)),
  ]);

  if (race === null || race === "missing") {
    return (
      <main className="mx-auto flex max-w-3xl flex-col items-start gap-4 px-4 py-24">
        <h1 className="display text-3xl sm:text-5xl">{t.missing.title}</h1>
        <p className="text-lg text-muted-foreground">{race === null ? t.unreachable : t.missing.lead(round, season)}</p>
        <Link href="/grand-prix" className="font-semibold text-primary">
          {t.missing.back} →
        </Link>
      </main>
    );
  }

  const raced = race.classification.length > 0;
  const prepared = debriefs?.filter((debrief) => debrief.subject.prepared) ?? [];
  const requested = debriefs?.filter((debrief) => !debrief.subject.prepared) ?? [];
  const waiting = requested.filter((debrief) => debrief.status === "waiting");
  const published = requested.filter((debrief) => debrief.status === "published");
  return (
    <main>
      <RaceHero summary={race.summary} race={race} />
      <div className="mx-auto max-w-6xl px-4 pt-10">
        {raced ? (
          <RaceTabs
            tabs={[
              {
                id: "result",
                label: t.tabs.result,
                content: (
                  <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
                    <ResultTable race={race} />
                    <RaceEvents race={race} />
                  </div>
                ),
              },
              { id: "grid", label: t.tabs.grid, content: <GridTable race={race} /> },
              {
                id: "race",
                label: t.tabs.race,
                content:
                  laps && laps !== "missing" ? (
                    <RaceCharts race={laps} />
                  ) : (
                    <p className="rounded-xl border bg-surface p-6 text-muted-foreground">{t.charts.unavailable}</p>
                  ),
              },
              { id: "strategy", label: t.tabs.strategy, content: <StrategyChart race={race} /> },
              { id: "standings", label: t.tabs.standings, content: <StandingsTables race={race} /> },
            ]}
          />
        ) : (
          <p className="rounded-xl border bg-surface p-6 text-muted-foreground">{t.noResults}</p>
        )}
      </div>

      {raced && (
        <section className="mx-auto max-w-6xl px-4 pt-16">
          <QuestionForm season={race.summary.season} round={race.summary.round} suggestions={raceSuggestions(race)} />
        </section>
      )}

      {prepared.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 pt-16">
          <SectionTitle>{t.prepared.title}</SectionTitle>
          <PreparedDebriefs debriefs={prepared} />
        </section>
      )}

      <section className="mx-auto max-w-6xl px-4 pt-16">
        <SectionTitle>{prepared.length > 0 ? t.debriefs.requested : t.debriefs.title}</SectionTitle>
        <div className="flex flex-col gap-6">
          {waiting.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {waiting.map((debrief) => (
                <DebriefCard key={debrief.id} debrief={debrief} />
              ))}
            </div>
          )}
          {published.length > 0 && <PublishedTable debriefs={published} />}
          {!waiting.length && !published.length && <p className="text-muted-foreground">{t.debriefs.empty}</p>}
        </div>
      </section>
    </main>
  );
}
