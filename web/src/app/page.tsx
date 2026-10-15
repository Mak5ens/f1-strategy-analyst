import { connection } from "next/server";
import { ApiStatus } from "@/components/api-status";
import { fetchInfo } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

export default async function Home() {
  // Rendered for each request, not at build time: the API's state is the one of now.
  await connection();
  const info = await fetchInfo();
  const t = getMessages().home;
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-12 sm:py-20">
      <h1 className="font-semibold text-3xl tracking-tight">{t.title}</h1>
      <p className="text-lg text-muted-foreground">{t.lead}</p>
      <ApiStatus info={info} />
      <p className="text-muted-foreground text-sm">{t.soon}</p>
    </main>
  );
}
