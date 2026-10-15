import type { Metadata } from "next";
import { connection } from "next/server";
import { FilterPills } from "@/components/filter-pills";
import { PageHeader } from "@/components/page-header";
import { PublishedTable } from "@/components/published-table";
import { fetchDebriefs } from "@/lib/api/client";
import { shortName } from "@/lib/format";
import { getMessages } from "@/lib/i18n";

const t = getMessages();

export const metadata: Metadata = { title: `${t.published.title} · ${t.metadata.title}` };

/** The published debriefs, `?saison=2025` and `&manche=16` to narrow them. */
export default async function Published({
  searchParams,
}: {
  searchParams: Promise<{ saison?: string; manche?: string }>;
}) {
  await connection();
  const query = await searchParams;
  const published = (await fetchDebriefs({ status: "published" })) ?? [];
  const seasons = [...new Set(published.map((debrief) => debrief.subject.season).filter((s) => s != null))].toSorted(
    (a, b) => b - a,
  );
  const season = seasons.find((year) => year === Number(query.saison));
  const inSeason = published.filter((debrief) => !season || debrief.subject.season === season);
  const races = new Map(
    inSeason
      .filter((debrief) => debrief.subject.round != null && debrief.subject.grand_prix)
      .map((debrief) => [debrief.subject.round as number, debrief.subject.grand_prix as string]),
  );
  const round = season && races.has(Number(query.manche)) ? Number(query.manche) : undefined;
  const shown = inSeason.filter((debrief) => !round || debrief.subject.round === round);
  return (
    <main>
      <PageHeader title={t.published.title} lead={t.published.lead}>
        <FilterPills
          pills={[
            { label: t.published.allSeasons, href: "/debriefs", active: !season },
            ...seasons.map((year) => ({
              label: String(year),
              href: `/debriefs?saison=${year}`,
              active: season === year,
            })),
          ]}
        />
        {season && races.size > 1 && (
          <FilterPills
            pills={[
              { label: t.published.allRaces, href: `/debriefs?saison=${season}`, active: !round },
              ...[...races.entries()]
                .toSorted(([a], [b]) => a - b)
                .map(([number, name]) => ({
                  label: shortName(name),
                  href: `/debriefs?saison=${season}&manche=${number}`,
                  active: round === number,
                })),
            ]}
          />
        )}
      </PageHeader>
      <section className="mx-auto max-w-6xl px-4 py-12">
        {shown.length ? (
          <PublishedTable debriefs={shown} />
        ) : (
          <p className="text-muted-foreground">{t.published.empty}</p>
        )}
      </section>
    </main>
  );
}
