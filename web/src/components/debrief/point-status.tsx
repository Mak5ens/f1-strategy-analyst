import { cn } from "cn";
import type { Point } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().debrief.review.pointStatus;

const tones: Record<string, string> = {
  verified: "bg-success/15 text-success",
  corrected: "bg-warning/15 text-warning",
  unverified: "bg-warning/20 text-warning",
  unavailable: "bg-surface-raised text-muted-foreground",
  draft: "bg-surface-raised text-muted-foreground",
};

/** What the agent's check said of a point: verified by code, or not. */
export function PointStatus({ status }: { status: Point["status"] }) {
  return (
    <span className={cn("rounded-full px-2.5 py-1 font-semibold text-xs uppercase tracking-wide", tones[status])}>
      {t[status] ?? status}
    </span>
  );
}
