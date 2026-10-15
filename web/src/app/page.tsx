import { connection } from "next/server";
import { DebriefCard } from "@/components/debrief-card";
import { NewDebriefForm } from "@/components/new-debrief-form";
import { PublishedTable } from "@/components/published-table";
import { SectionTitle } from "@/components/section-title";
import { fetchDebriefs } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

export default async function Home() {
  // Rendered for each request: what waits for the analyst is the state of now.
  await connection();
  const [waiting, published] = await Promise.all([fetchDebriefs("waiting"), fetchDebriefs("published")]);
  const t = getMessages().home;
  const now = new Date();
  return (
    <main>
      <section className="relative overflow-hidden border-b bg-band">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-0 w-1/2 bg-[repeating-linear-gradient(115deg,transparent_0_46px,rgb(255_255_255/0.025)_46px_92px)] [mask-image:linear-gradient(to_left,black,transparent)]"
        />
        <div className="relative mx-auto flex max-w-6xl flex-col gap-6 px-4 py-16 sm:py-24">
          <p className="flex items-center gap-2 font-semibold text-primary text-sm uppercase tracking-wider">
            <span className="slash" aria-hidden />
            {t.eyebrow}
          </p>
          <h1 className="display max-w-4xl text-4xl sm:text-6xl">{t.title}</h1>
          <p className="max-w-2xl text-lg text-muted-foreground">{t.lead}</p>
          <div className="max-w-3xl">
            <NewDebriefForm />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pt-16">
        <SectionTitle>{t.waitingTitle}</SectionTitle>
        {waiting?.length ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {waiting.map((debrief) => (
              <DebriefCard key={debrief.id} debrief={debrief} now={now} />
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground">{t.waitingEmpty}</p>
        )}
      </section>

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
