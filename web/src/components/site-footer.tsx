import { ApiStatus } from "@/components/api-status";
import { fetchInfo } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

export async function SiteFooter() {
  const info = await fetchInfo();
  return (
    <footer className="mt-24 border-t bg-band">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-muted-foreground text-xs sm:flex-row sm:items-center sm:justify-between">
        <p>{getMessages().footer.disclaimer}</p>
        <ApiStatus info={info} />
      </div>
    </footer>
  );
}
