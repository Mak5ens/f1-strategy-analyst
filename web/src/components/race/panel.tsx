import { cn } from "cn";
import type { ReactNode } from "react";

/** The black panel tables sit on, scrolling sideways on a phone rather than squeezing. */
export function Panel({
  children,
  className,
  min = "36rem",
}: {
  children: ReactNode;
  className?: string;
  min?: string;
}) {
  return (
    <div className={cn("overflow-x-auto rounded-xl bg-band px-2 sm:px-6", className)}>
      <div style={{ minWidth: min }}>{children}</div>
    </div>
  );
}

export const th = "py-4 pr-4 font-semibold";
export const thead = "text-muted-foreground text-xs uppercase tracking-wide";
export const row = "border-b transition-colors last:border-0 hover:bg-hover";
