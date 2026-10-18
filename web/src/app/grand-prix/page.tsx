import type { Metadata } from "next";
import { connection } from "next/server";
import { RaceCard } from "@/components/race/race-card";
import { SeasonPicker } from "@/components/race/season-picker";
import { fetchRaces, fetchSeasons } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().calendar;

export const metadata: Metadata = { title: `${getMessages().nav.races} · ${getMessages().metadata.title}` };

/** The calendar of a season, `?saison=2024` for another one than the latest. */
export default async function Calendar({ searchParams }: { searchParams: Promise<{ saison?: string }> }) {
  await connection();
  const seasons = await fetchSeasons();
  const asked = Number((await searchParams).saison);
  const season = seasons?.includes(asked) ? asked : seasons?.[0];
  const races = season ? await fetchRaces(season) : null;
  return (
    <main>
      <section className="border-b bg-band">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 pt-12 pb-8 sm:pt-16">
          <p className="flex items-center gap-2 font-semibold text-primary text-sm uppercase tracking-wider">
            <span className="slash" aria-hidden />
            {t.eyebrow}
          </p>
          <h1 className="display text-4xl sm:text-6xl">{season ? t.title(season) : t.eyebrow}</h1>
          <p className="max-w-2xl text-lg text-muted-foreground">{t.lead}</p>
          {seasons && seasons.length > 1 && (
            <div className="mt-4">
              <SeasonPicker seasons={seasons} current={season ?? 0} href={(year) => `/grand-prix?saison=${year}`} />
            </div>
          )}
        </div>
      </section>
      <section className="mx-auto max-w-6xl px-4 py-12">
        {seasons === null ? (
          <p className="text-muted-foreground">{t.unreachable}</p>
        ) : races?.length ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {races.map((race) => (
              <RaceCard key={race.round} race={race} />
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground">{t.empty}</p>
        )}
      </section>
    </main>
  );
}
