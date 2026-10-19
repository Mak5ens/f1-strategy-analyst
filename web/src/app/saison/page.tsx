import type { Metadata } from "next";
import { connection } from "next/server";
import { ChampionshipChart, ResultsGrid, SeasonSummary, TeamPace } from "@/components/season/season-view";
import { fetchSeasonOverview, fetchSeasons } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().season;

export const metadata: Metadata = { title: `${getMessages().nav.season} · ${getMessages().metadata.title}` };

type Search = Promise<{ saison?: string }>;

/**
 * A season told by its numbers (LAB-215), `?saison=2025`; the latest by default. Every number comes from the API's
 * `f1.season`, computed by code. The season form is a plain GET: it works without JavaScript.
 */
export default async function SeasonPage({ searchParams }: { searchParams: Search }) {
  await connection();
  const asked = await searchParams;
  const seasons = await fetchSeasons();
  const season = seasons?.includes(Number(asked.saison)) ? Number(asked.saison) : seasons?.[0];
  const overview = season ? await fetchSeasonOverview(season) : null;
  const found = overview && overview !== "missing" ? overview : null;
  return (
    <main>
      <section className="border-b bg-band">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 pt-12 pb-8 sm:pt-16">
          <p className="flex items-center gap-2 font-semibold text-primary text-sm uppercase tracking-wider">
            <span className="slash" aria-hidden />
            {t.eyebrow}
          </p>
          <h1 className="display text-4xl sm:text-6xl">{season ? t.title(season) : t.eyebrow}</h1>
          <p className="max-w-3xl text-lg text-muted-foreground">{t.lead}</p>
          {seasons && seasons.length > 1 && (
            <form action="/saison" className="mt-4 flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-muted-foreground text-xs uppercase tracking-wide">
                {t.pick}
                <select name="saison" defaultValue={season} className="rounded-md border bg-surface px-3 py-2 text-sm">
                  {seasons.map((year) => (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="submit"
                className="rounded-md bg-primary px-4 py-2 font-semibold text-primary-foreground text-sm"
              >
                {t.show}
              </button>
            </form>
          )}
        </div>
      </section>
      <div className="mx-auto flex max-w-6xl flex-col gap-12 px-4 py-12">
        {seasons === null || overview === null ? (
          <p className="text-muted-foreground">{t.unreachable}</p>
        ) : !found ? (
          <p className="text-muted-foreground">{t.missing}</p>
        ) : (
          <>
            <SeasonSummary season={found} />
            <ChampionshipChart season={found} />
            <ResultsGrid season={found} />
            <TeamPace season={found} />
          </>
        )}
      </div>
    </main>
  );
}
