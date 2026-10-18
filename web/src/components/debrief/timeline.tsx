import { cn } from "cn";
import type { ReactNode } from "react";
import type { Point } from "@/lib/api/client";

/** Where each moment stands on the timeline: the first and the last close the line. */
export function timelinePlaces(points: Point[]): Map<string, { first: boolean; last: boolean }> {
  const moments = points.filter((point) => point.kind === "point");
  return new Map(moments.map((point, index) => [point.id, { first: index === 0, last: index === moments.length - 1 }]));
}

// The dot's centre, level with the head of the card (its padding and half a line of title).
const DOT = "top-[1.6rem]";

/** A part of the debrief: the summary and the takeaway as they are, a moment on the race's timeline, its lap on the
 * left (above its title on a phone) and a line joining it to the moments before and after (LAB-207). The card's style goes in `className`. */
export function DebriefPart({
  point,
  place,
  className,
  children,
}: {
  point: Point;
  place?: { first: boolean; last: boolean };
  className: string;
  children: ReactNode;
}) {
  if (!place) return <li className={className}>{children}</li>;
  return (
    <li className="grid grid-cols-[0.75rem_1fr] gap-3 sm:grid-cols-[5.5rem_1fr] sm:gap-4">
      <div className="relative" aria-hidden={!point.when}>
        {!place.first && <span className="absolute -top-4 right-[5px] h-[2.6rem] w-px bg-border" />}
        {!place.last && <span className={cn("absolute right-[5px] -bottom-0 w-px bg-border", DOT)} />}
        <span
          className={cn(
            "absolute right-0 size-[11px] -translate-y-1/2 rounded-full border-2 border-primary bg-background",
            DOT,
          )}
        />
        {point.when && (
          <span
            className={cn(
              "figures absolute right-5 hidden -translate-y-1/2 sm:block text-right font-semibold text-muted-foreground text-xs uppercase leading-tight tracking-wide",
              DOT,
            )}
          >
            {point.when}
          </span>
        )}
      </div>
      <div className={className}>{children}</div>
    </li>
  );
}
