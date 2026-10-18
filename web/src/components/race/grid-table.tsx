import { cn } from "cn";
import type { Race } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { DriverCell } from "./driver-cell";
import { Panel, row, th, thead } from "./panel";

const t = getMessages().race.grid;

/** Places won or lost: green up, red down, nothing for a driver who kept their place or did not finish. */
export function PlacesGained({ places }: { places: number | null }) {
  if (places == null || places === 0) return <span className="text-muted-foreground">–</span>;
  return (
    <span className={cn("figures font-semibold", places > 0 ? "text-success" : "text-destructive")}>
      {places > 0 ? `▲ ${places}` : `▼ ${-places}`}
    </span>
  );
}

/** The starting grid in order, with where each driver finished. */
export function GridTable({ race }: { race: Race }) {
  const grid = race.classification
    .filter((entry) => entry.grid != null)
    .toSorted((a, b) => (a.grid || 99) - (b.grid || 99));
  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-sm">{t.lead}</p>
      <Panel min="28rem">
        <table className="w-full text-left text-sm">
          <thead className={thead}>
            <tr className="border-b">
              <th className={cn(th, "w-16")}>{t.start}</th>
              <th className={th}>{getMessages().race.result.driver}</th>
              <th className={cn(th, "text-right")}>{t.finish}</th>
              <th className="py-4 text-right font-semibold">{t.change}</th>
            </tr>
          </thead>
          <tbody>
            {grid.map((entry) => (
              <tr key={entry.driver.code} className={row}>
                <td className="display figures py-3 pr-4 text-base">{entry.grid || t.pitLane}</td>
                <td className="py-3 pr-4">
                  <DriverCell driver={entry.driver} />
                </td>
                <td className="figures py-3 pr-4 text-right">
                  {getMessages().race.result.positions[entry.position_text] ?? entry.position_text}
                </td>
                <td className="py-3 text-right">
                  <PlacesGained places={entry.places_gained} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
