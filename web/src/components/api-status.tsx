import { cn } from "cn";
import type { Info } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

/** Whether the API answers, and the version of the app behind it. */
export function ApiStatus({ info }: { info: Info | null }) {
  const t = getMessages().apiStatus;
  return (
    <p className="flex items-center gap-2 whitespace-nowrap" title={info ? undefined : t.unreachable}>
      <span className={cn("size-2 rounded-full", info ? "bg-success" : "bg-destructive")} aria-hidden />
      <span>{info ? t.up : t.down}</span>
      {info && <span className="figures">· {t.version(info.version)}</span>}
    </p>
  );
}
