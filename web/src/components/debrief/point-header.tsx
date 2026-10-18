import { cn } from "cn";
import type { Point } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { PointStatus } from "./point-status";

const t = getMessages().debrief.parts;

/** The rank of each moment among the points, the summary and the takeaway aside. */
export function momentNumbers(points: Point[]): Map<string, number> {
  const moments = points.filter((point) => point.kind === "point");
  return new Map(moments.map((point, index) => [point.id, index + 1]));
}

/** The head of a point: "Résumé", "À retenir", or the moment's number and title, its lap above on a phone (LAB-207);
 * then its status. */
export function PointHeader({ point, number }: { point: Point; number?: number }) {
  const label = point.kind === "summary" ? t.summary : point.kind === "takeaway" ? t.takeaway : null;
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex flex-col gap-1">
        {point.when && (
          <span className="figures font-semibold text-muted-foreground text-xs uppercase tracking-wide sm:hidden">
            {point.when}
          </span>
        )}
        <div className="flex items-baseline gap-3">
          {label ? (
            <span className="font-semibold text-primary text-xs uppercase tracking-wider">{label}</span>
          ) : (
            <span className="display figures text-muted-foreground text-xl">
              {String(number ?? 0).padStart(2, "0")}
            </span>
          )}
          {point.title && <h3 className={cn("font-semibold text-lg leading-snug")}>{point.title}</h3>}
        </div>
      </div>
      <PointStatus status={point.status} />
    </div>
  );
}

/** How a point's card stands out: the summary as a lead, the takeaway as a conclusion. */
export function partStyle(point: Point): string {
  if (point.kind === "summary") return "border-primary/40 bg-band";
  if (point.kind === "takeaway") return "border-l-4 border-l-primary";
  return "";
}
