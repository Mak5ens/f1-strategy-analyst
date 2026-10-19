import { PointChart } from "@/components/race/point-chart";
import type { Fact, Point, RaceLaps, Source } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";

const t = getMessages().debrief.review;
const charts = getMessages().race.charts;

/**
 * Where a point's numbers and rules come from: the analyses it cites, with the race chart that shows each when the
 * race's laps are given (LAB-189), and the FIA passages, opened on a click.
 */
export function PointEvidence({
  point,
  evidence,
  laps,
}: {
  point: Point;
  evidence: { facts: Fact[]; sources: Source[] };
  laps?: RaceLaps | null;
}) {
  const facts = evidence.facts.filter((fact) => point.facts.includes(fact.id));
  const charted = laps ? facts.filter((fact) => fact.chart) : [];
  const sources = evidence.sources.filter((source) => point.sources.includes(source.id));
  if (!facts.length && !sources.length) return null;
  return (
    <div className="flex flex-col gap-3 text-sm">
      {facts.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.figures}</span>
          {facts.map((fact) => (
            <span key={fact.id} className="rounded-full bg-band px-2.5 py-1 text-xs" title={fact.error ?? undefined}>
              {fact.label}
              {!fact.ok && <span className="text-destructive"> · {t.failed}</span>}
            </span>
          ))}
        </div>
      )}
      {laps &&
        charted.map(
          (fact) =>
            fact.chart && (
              <details key={fact.id} className="group rounded-lg bg-band px-3 py-2">
                <summary className="cursor-pointer font-medium text-xs marker:text-primary-text">
                  {charts.showChart} · {fact.label}
                </summary>
                <div className="mt-3">
                  <PointChart race={laps} chart={fact.chart} label={fact.label} />
                </div>
              </details>
            ),
        )}
      {sources.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="text-muted-foreground text-xs uppercase tracking-wide">{t.sources}</span>
          {sources.map((source) => (
            <details key={source.id} className="group rounded-lg bg-band px-3 py-2">
              <summary className="cursor-pointer font-medium text-xs marker:text-primary-text">{source.label}</summary>
              <p className="mt-2 whitespace-pre-line text-muted-foreground text-xs leading-relaxed">{source.text}</p>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
