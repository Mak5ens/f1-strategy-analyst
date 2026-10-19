import { cn } from "cn";
import Link from "next/link";
import type { CSSProperties } from "react";
import { Panel, row, th, thead } from "@/components/race/panel";
import type { Duel } from "@/lib/api/client";
import { duelColours, favours } from "@/lib/duel";
import { getMessages } from "@/lib/i18n";
import { scale } from "@/lib/race-chart";

const t = getMessages().duel;
const gaps = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
  signDisplay: "exceptZero",
});
const points = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

function colours(duel: Duel) {
  const [first, second] = duelColours(duel);
  return { "--first": first, "--second": second } as CSSProperties;
}

/** The season in a few numbers: who was ahead how often, the points, and the median gaps. */
export function DuelSummary({ duel }: { duel: Duel }) {
  const { summary } = duel;
  const score = (label: string, a: number, b: number, note?: string) => (
    <div className="flex flex-col gap-1 rounded-xl border bg-surface p-4">
      <span className="text-muted-foreground text-xs uppercase tracking-wide">{label}</span>
      <span className="figures display text-3xl">
        <span className="text-[var(--first)]">{points.format(a)}</span>
        <span className="px-2 text-muted-foreground">–</span>
        <span className="text-[var(--second)]">{points.format(b)}</span>
      </span>
      {note && <span className="text-muted-foreground text-xs">{note}</span>}
    </div>
  );
  const gap = (label: string, value: number | null) => {
    const ahead = favours(duel, value);
    return (
      <div className="flex flex-col gap-1 rounded-xl border bg-surface p-4">
        <span className="text-muted-foreground text-xs uppercase tracking-wide">{label}</span>
        <span className="figures display text-3xl">{value === null ? "—" : t.seconds(gaps.format(value))}</span>
        <span className="text-muted-foreground text-xs">{ahead ? t.ahead(ahead.name) : t.even}</span>
      </div>
    );
  };
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5" style={colours(duel)}>
      {score(t.qualifying, summary.qualifying_first, summary.qualifying_second)}
      {score(t.race, summary.race_first, summary.race_second)}
      {score(t.points, summary.points_first, summary.points_second, t.pointsNote)}
      {gap(t.qualifyingGap, summary.qualifying_gap_s)}
      {gap(t.paceGap, summary.pace_gap_s)}
    </div>
  );
}

const W = 960;
const H = 220;
const M = { top: 22, right: 12, bottom: 28, left: 56 };

/**
 * A gap round by round as bars from zero: up, the first driver was faster, in their colour; down, the second. A
 * round without a gap (a driver absent, too few clean laps) has no bar.
 */
export function DuelChart({ duel, kind }: { duel: Duel; kind: "qualifying" | "pace" }) {
  const values = duel.rounds.map((round) => ({
    round,
    gap: kind === "qualifying" ? (round.qualifying?.gap_s ?? null) : (round.pace?.gap_s ?? null),
  }));
  const extent = Math.max(0.1, ...values.map((value) => Math.abs(value.gap ?? 0)));
  // Faster up: a negative gap (the first driver faster) goes above zero.
  const y = scale([extent, -extent], [H - M.bottom, M.top]);
  const band = (W - M.left - M.right) / Math.max(1, values.length);
  return (
    <Panel min="40rem" className="py-3">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={kind === "qualifying" ? t.chartQualifying : t.chartPace}
        className="block h-auto w-full"
        style={colours(duel)}
      >
        <line
          x1={M.left}
          x2={W - M.right}
          y1={y(0)}
          y2={y(0)}
          className="stroke-muted-foreground"
          strokeOpacity={0.4}
        />
        <text x={M.left - 8} y={M.top} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--first)" fontWeight={700}>
          {duel.first.code}
        </text>
        <text
          x={M.left - 8}
          y={H - M.bottom}
          dy="0.32em"
          textAnchor="end"
          fontSize={11}
          fill="var(--second)"
          fontWeight={700}
        >
          {duel.second.code}
        </text>
        {values.map(({ round, gap }, index) => {
          const x = M.left + index * band;
          return (
            <g key={round.round}>
              {gap !== null && (
                <rect
                  data-round={round.round}
                  x={x + band * 0.18}
                  width={band * 0.64}
                  y={Math.min(y(0), y(gap))}
                  height={Math.max(1, Math.abs(y(gap) - y(0)))}
                  rx={2}
                  fill={gap < 0 ? "var(--first)" : "var(--second)"}
                >
                  <title>{`${round.grand_prix} · ${t.seconds(gaps.format(gap))}`}</title>
                </rect>
              )}
              <text x={x + band / 2} y={H - 8} textAnchor="middle" fontSize={11} className="fill-muted-foreground">
                {round.round}
              </text>
            </g>
          );
        })}
      </svg>
    </Panel>
  );
}

/** Round by round: the qualifying gap and places, the race places and points, the pace gap; a link to the race. */
export function DuelTable({ duel }: { duel: Duel }) {
  const pilots = `${duel.first.code},${duel.second.code}`;
  const gap = (value: number | null | undefined) => (value == null ? "—" : t.seconds(gaps.format(value)));
  return (
    <Panel min="48rem">
      <table className="w-full text-sm" style={colours(duel)}>
        <thead className={thead}>
          <tr className="border-b">
            <th className={cn(th, "text-left")}>{t.round}</th>
            <th className={cn(th, "text-left")}>{t.grandPrix}</th>
            <th className={cn(th, "text-right")}>{t.qualifying}</th>
            <th className={cn(th, "text-right")}>{t.race}</th>
            <th className={cn(th, "text-right")}>{t.paceGap}</th>
          </tr>
        </thead>
        <tbody className="figures">
          {duel.rounds.map((round) => (
            <tr key={round.round} className={row}>
              <td className="py-3 pr-4">{round.round}</td>
              <td className="py-3 pr-4">
                <Link
                  href={`/grand-prix/${duel.season}/${round.round}?onglet=course&pilotes=${pilots}`}
                  className="font-semibold hover:text-primary-text"
                >
                  {round.grand_prix}
                </Link>
              </td>
              <td className="py-3 pr-4 text-right">
                {round.qualifying ? (
                  <>
                    {gap(round.qualifying.gap_s)}
                    <span className="text-muted-foreground">
                      {[
                        "",
                        round.qualifying.part,
                        `P${round.qualifying.first_position} / P${round.qualifying.second_position}`,
                      ]
                        .filter((part) => part !== null)
                        .join(" · ")}
                    </span>
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td className="py-3 pr-4 text-right">
                {round.race ? (
                  <>
                    <span className="text-[var(--first)]">{round.race.first_text}</span>
                    {" / "}
                    <span className="text-[var(--second)]">{round.race.second_text}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {points.format(round.race.first_points)}–{points.format(round.race.second_points)} pts
                    </span>
                  </>
                ) : (
                  <span className="text-muted-foreground">{t.noRace}</span>
                )}
              </td>
              <td className="py-3 pr-4 text-right">
                {round.pace ? (
                  <>
                    {gap(round.pace.gap_s)}
                    <span className="text-muted-foreground"> · {t.laps(round.pace.laps)}</span>
                  </>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
