import type { Metadata } from "next";
import { connection } from "next/server";
import { DuelChart, DuelSummary, DuelTable } from "@/components/duel/duel-view";
import { SectionTitle } from "@/components/section-title";
import { fetchDuel, fetchSeasonDrivers, fetchSeasons } from "@/lib/api/client";
import { defaultPair } from "@/lib/duel";
import { getMessages } from "@/lib/i18n";

const t = getMessages().duel;

export const metadata: Metadata = { title: `${getMessages().nav.duel} · ${getMessages().metadata.title}` };

type Search = Promise<{ saison?: string; a?: string; b?: string }>;

/**
 * Two drivers face to face over a season (LAB-212), `?saison=2025&a=LEC&b=HAM`; the season's leader and their
 * teammate by default. The form is a plain GET: it works without JavaScript.
 */
export default async function DuelPage({ searchParams }: { searchParams: Search }) {
  await connection();
  const asked = await searchParams;
  const seasons = await fetchSeasons();
  const season = seasons?.includes(Number(asked.saison)) ? Number(asked.saison) : seasons?.[0];
  const drivers = season ? await fetchSeasonDrivers(season) : null;
  const pair = drivers ? defaultPair(drivers, [asked.a, asked.b]) : null;
  const duel = season && pair ? await fetchDuel(season, pair) : null;
  const found = duel && duel !== "missing" ? duel : null;
  const select = "rounded-md border bg-surface px-3 py-2 text-sm";
  return (
    <main>
      <section className="border-b bg-band">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 pt-12 pb-8 sm:pt-16">
          <p className="flex items-center gap-2 font-semibold text-primary-text text-sm uppercase tracking-wider">
            <span className="slash" aria-hidden />
            {t.eyebrow}
          </p>
          <h1 className="display text-4xl sm:text-6xl">
            {found ? t.title(found.first.name, found.second.name) : t.eyebrow}
          </h1>
          <p className="max-w-3xl text-lg text-muted-foreground">{t.lead}</p>
          {seasons && drivers && pair && (
            <form action="/duel" className="mt-4 flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-muted-foreground uppercase tracking-wide">
                {t.season}
                <select name="saison" defaultValue={season} className={select}>
                  {seasons.map((year) => (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
              </label>
              {(["a", "b"] as const).map((name, index) => (
                <label key={name} className="flex flex-col gap-1 text-xs text-muted-foreground uppercase tracking-wide">
                  {index === 0 ? t.first : t.second}
                  <select name={name} defaultValue={pair[index]} className={select}>
                    {drivers.map((driver) => (
                      <option key={driver.code} value={driver.code}>
                        {driver.name}
                        {driver.team ? ` · ${driver.team}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <button
                type="submit"
                className="rounded-md bg-primary px-4 py-2 font-semibold text-primary-foreground text-sm"
              >
                {t.compare}
              </button>
            </form>
          )}
        </div>
      </section>
      <div className="enter mx-auto flex max-w-6xl flex-col gap-10 px-4 py-12">
        {seasons === null || duel === null ? (
          <p className="text-muted-foreground">{t.unreachable}</p>
        ) : !found ? (
          <p className="text-muted-foreground">{t.missing}</p>
        ) : (
          <>
            <DuelSummary duel={found} />
            <section className="flex flex-col gap-3">
              <SectionTitle>{t.chartQualifying}</SectionTitle>
              <p className="text-muted-foreground text-sm">{t.chartQualifyingLead}</p>
              <DuelChart duel={found} kind="qualifying" />
            </section>
            <section className="flex flex-col gap-3">
              <SectionTitle>{t.chartPace}</SectionTitle>
              <p className="text-muted-foreground text-sm">{t.chartPaceLead}</p>
              <DuelChart duel={found} kind="pace" />
            </section>
            <DuelTable duel={found} />
          </>
        )}
      </div>
    </main>
  );
}
