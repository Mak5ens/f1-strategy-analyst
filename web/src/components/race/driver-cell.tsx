import type { CSSProperties } from "react";
import type { Driver } from "@/lib/api/client";

/** The style that gives a block its team's colour, as `--team`; grey when the data has none. */
export function teamStyle(colour: string | null | undefined): CSSProperties {
  return { "--team": colour ?? "var(--muted-foreground)" } as CSSProperties;
}

/** A driver in a table: a bar of the team's colour, the name, and the team under it on wide screens. */
export function DriverCell({ driver, team = true }: { driver: Driver; team?: boolean }) {
  return (
    <span className="flex items-center gap-3" style={teamStyle(driver.colour)}>
      <span className="h-6 w-1 shrink-0 rounded-full bg-[var(--team)]" aria-hidden />
      <span className="min-w-0">
        <span className="block truncate font-semibold">{driver.name}</span>
        {team && driver.team && <span className="block truncate text-muted-foreground text-xs">{driver.team}</span>}
      </span>
    </span>
  );
}
