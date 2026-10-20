import type { Metadata } from "next";
import { connection } from "next/server";
import { ReservedPage } from "@/components/analyst-only";
import { DebriefCard } from "@/components/debrief-card";
import { FilterPills } from "@/components/filter-pills";
import { PageHeader } from "@/components/page-header";
import { fetchDebriefs, fetchSession, isAnalyst, type Stop } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages();

export const metadata: Metadata = { title: `${t.waiting.title} · ${t.metadata.title}` };

const stops: Stop[] = ["clarification", "plan", "review"];

/** Every request waiting for the analyst, `?arret=plan` for one stop. */
export default async function Waiting({ searchParams }: { searchParams: Promise<{ arret?: string }> }) {
  await connection();
  if (!isAnalyst(await fetchSession())) return <ReservedPage back="/en-attente" />;
  const asked = (await searchParams).arret;
  const stop = stops.find((name) => name === asked);
  const waiting = await fetchDebriefs({ status: "waiting" });
  const shown = waiting?.filter((debrief) => !stop || debrief.waiting === stop) ?? [];
  const count = (name: Stop) => waiting?.filter((debrief) => debrief.waiting === name).length ?? 0;
  return (
    <main>
      <PageHeader title={t.waiting.title} lead={t.waiting.lead}>
        <FilterPills
          pills={[
            { label: `${t.waiting.all} (${waiting?.length ?? 0})`, href: "/en-attente", active: !stop },
            ...stops.map((name) => ({
              label: `${t.stops[name].label} (${count(name)})`,
              href: `/en-attente?arret=${name}`,
              active: stop === name,
            })),
          ]}
        />
      </PageHeader>
      <section className="mx-auto max-w-6xl px-4 py-12">
        {shown.length ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((debrief) => (
              <DebriefCard key={debrief.id} debrief={debrief} />
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground">{t.waiting.empty}</p>
        )}
      </section>
    </main>
  );
}
