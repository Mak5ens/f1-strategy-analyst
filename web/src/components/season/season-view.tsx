"use client";

import { cn } from "cn";
import Link from "next/link";
import { type KeyboardEvent, type PointerEvent, useState } from "react";
import { teamStyle } from "@/components/race/driver-cell";
import { Panel, row, th, thead } from "@/components/race/panel";
import type { SeasonOverview } from "@/lib/api/client";
import { getMessages } from "@/lib/i18n";
import { path, scale, spread, ticks } from "@/lib/race-chart";
import { championship, type Line, leaders, median, pace, tone } from "@/lib/season";

const t = getMessages().season;
const points = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const percent = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** The season in four numbers: the leader and their lead, the rounds raced, the leading team, the driver in form. */
export function SeasonSummary({ season }: { season: SeasonOverview }) {
  const [first, second] = season.drivers;
  const [team] = season.teams;
  const form = season.drivers.toSorted((a, b) => b.form_points - a.form_points)[0];
  const card = (label: string, value: string, note: string | null, colour?: string | null) => (
    <div className="flex min-w-0 flex-col gap-1 rounded-xl border bg-surface p-4" style={teamStyle(colour)}>
      <span className="text-muted-foreground text-xs uppercase tracking-wide">{label}</span>
      <span className={cn("display break-words text-lg sm:text-2xl", colour && "text-[var(--team)]")}>{value}</span>
      {note && <span className="figures text-muted-foreground text-xs">{note}</span>}
    </div>
  );
  const lead = first && second ? first.points - second.points : null;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {first &&
        card(
          t.leader,
          first.driver.name,
          lead === null || !second
            ? t.points(points.format(first.points))
            : lead === 0
              ? t.tied(second.driver.name)
              : t.leaderNote(t.points(points.format(lead)), second.driver.name),
          first.driver.colour,
        )}
      {card(t.rounds, String(season.rounds.length), t.roundsNote(season.rounds.filter((round) => round.sprint).length))}
      {team && card(t.teamLeader, team.team, t.points(points.format(team.points)), team.colour)}
      {form &&
        card(
          t.form,
          form.driver.name,
          t.formNote(season.form_rounds, t.points(points.format(form.form_points))),
          form.driver.colour,
        )}
    </div>
  );
}

/** The championship round by round, drivers or teams, the first five highlighted. */
export function ChampionshipChart({ season }: { season: SeasonOverview }) {
  const [kind, setKind] = useState<"drivers" | "teams">("drivers");
  const lines = championship(season, kind);
  const top = Math.max(1, ...lines.flatMap((line) => line.values.filter((value): value is number => value !== null)));
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="display text-2xl">{t.championship}</h2>
          <p className="text-muted-foreground text-sm">{t.championshipLead}</p>
        </div>
        <Toggle
          label={t.championship}
          options={[
            ["drivers", t.drivers],
            ["teams", t.teams],
          ]}
          value={kind}
          onChange={setKind}
        />
      </div>
      <RoundChart
        key={kind}
        label={`${t.championship} · ${kind === "drivers" ? t.drivers : t.teams}`}
        season={season}
        lines={lines}
        domain={[top, 0]}
        format={(value) => points.format(value)}
        unit={(value) => t.points(points.format(value))}
      />
    </section>
  );
}

/** The teams' gaps to the fastest, round by round, in qualifying or in the race, with their season's median. */
export function TeamPace({ season }: { season: SeasonOverview }) {
  const [kind, setKind] = useState<"qualifying" | "race">("race");
  const lines = pace(season, kind);
  const medians = lines
    .map((line) => ({ line, found: median(line.values) }))
    .toSorted((a, b) => (a.found?.value ?? Number.POSITIVE_INFINITY) - (b.found?.value ?? Number.POSITIVE_INFINITY));
  const measured = lines.flatMap((line) => line.values.filter((value): value is number => value !== null)).toSorted();
  // Up to the 95th percentile: one round where a team was far off (a wet race, a crash in Q1) should not flatten
  // the rest. The line leaves the chart there, and the table keeps the number.
  const high = Math.max(0.5, Math.ceil((measured[Math.floor(measured.length * 0.95)] ?? 1) * 2) / 2);
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="display text-2xl">{t.pace}</h2>
          <p className="max-w-3xl text-muted-foreground text-sm">{t.paceLead[kind]}</p>
        </div>
        <Toggle
          label={t.pace}
          options={[
            ["race", t.race],
            ["qualifying", t.qualifying],
          ]}
          value={kind}
          onChange={setKind}
        />
      </div>
      <RoundChart
        key={kind}
        label={`${t.pace} · ${kind === "race" ? t.race : t.qualifying}`}
        season={season}
        lines={lines}
        domain={[0, high]}
        format={(value) => `${percent.format(value)} %`}
        unit={(value) => t.percent(percent.format(value))}
        initial={medians.slice(0, 5).map(({ line }) => line.code)}
      />
      <Panel min="28rem">
        <table className="w-full text-sm">
          <thead className={thead}>
            <tr className="border-b text-left">
              <th className={th}>{t.team}</th>
              <th className={cn(th, "text-right")}>{t.median}</th>
              <th className={cn(th, "pr-0 text-right")}>{t.measuredColumn}</th>
            </tr>
          </thead>
          <tbody>
            {medians.map(({ line, found }) => (
              <tr key={line.code} className={row}>
                <td className="py-3 pr-4 font-semibold" style={teamStyle(line.colour)}>
                  <span className="mr-2 inline-block h-3 w-1 rounded-full bg-[var(--team)] align-middle" aria-hidden />
                  {line.label}
                </td>
                <td className="figures py-3 pr-4 text-right">{found ? t.percent(percent.format(found.value)) : "—"}</td>
                <td className="figures py-3 text-right text-muted-foreground">
                  {t.measured(found?.count ?? 0, season.rounds.length)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </section>
  );
}

const tones: Record<string, string> = {
  win: "bg-primary font-bold text-primary-foreground",
  podium: "bg-warning/20 font-bold text-warning",
  points: "bg-success/10 text-foreground",
  plain: "text-muted-foreground",
  out: "text-destructive",
  none: "text-muted-foreground/40",
};

/** Every driver's result round by round, in championship order, with their points and form; each round a link. */
export function ResultsGrid({ season }: { season: SeasonOverview }) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="display text-2xl">{t.results}</h2>
        <p className="max-w-3xl text-muted-foreground text-sm">{t.resultsLead(season.form_rounds)}</p>
      </div>
      <Panel min={`${14 + season.rounds.length * 2.1}rem`}>
        <table className="w-full text-sm">
          <thead className={thead}>
            <tr className="border-b text-left">
              <th className={cn(th, "sticky left-0 z-10 bg-band")}>{t.driver}</th>
              {season.rounds.map((round) => (
                <th key={round.round} className="px-px py-4 text-center font-semibold">
                  <Link
                    href={`/grand-prix/${season.season}/${round.round}`}
                    title={round.grand_prix}
                    className="hover:text-foreground"
                  >
                    {round.round}
                  </Link>
                </th>
              ))}
              <th className={cn(th, "pl-3 text-right")}>{t.total}</th>
              <th className={cn(th, "pr-0 text-right")}>{t.formColumn}</th>
            </tr>
          </thead>
          <tbody>
            {season.drivers.map((one) => (
              <tr key={one.driver.code} className={row}>
                <td className="sticky left-0 z-10 bg-band py-2 pr-4" style={teamStyle(one.driver.colour)}>
                  <span className="figures mr-2 inline-block w-5 text-muted-foreground">{one.position}</span>
                  <span className="mr-2 inline-block h-3 w-1 rounded-full bg-[var(--team)] align-middle" aria-hidden />
                  <span className="font-semibold" title={one.driver.name}>
                    {one.driver.code}
                  </span>
                </td>
                {one.results.map((result, index) => {
                  const round = season.rounds[index];
                  return (
                    <td key={round?.round ?? index} className="px-px py-1 text-center">
                      <span
                        data-tone={tone(result)}
                        title={round ? `${round.grand_prix} · ${result?.text ?? "—"}` : undefined}
                        className={cn(
                          "figures inline-flex h-7 w-7 items-center justify-center rounded text-xs",
                          tones[tone(result)],
                        )}
                      >
                        {result ? result.text || "—" : "·"}
                      </span>
                    </td>
                  );
                })}
                <td className="figures py-2 pl-3 text-right font-semibold">{points.format(one.points)}</td>
                <td className="figures py-2 text-right text-muted-foreground">{points.format(one.form_points)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </section>
  );
}

function Toggle<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: [T, string][];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="flex rounded-full border p-1">
      <legend className="sr-only">{label}</legend>
      {options.map(([key, text]) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          onClick={() => onChange(key)}
          className={cn(
            "rounded-full px-3 py-1 font-semibold text-xs transition-colors",
            value === key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {text}
        </button>
      ))}
    </fieldset>
  );
}

const W = 960;
const H = 360;
const M = { top: 14, right: 96, bottom: 28, left: 56 };

/**
 * Rounds across, a value down, one line per driver or team: the highlighted ones in their colour and named at their
 * end, the others faded. Hovering or the arrow keys read one round, for the highlighted lines.
 */
function RoundChart({
  label,
  season,
  lines,
  domain,
  format,
  unit,
  initial,
}: {
  label: string;
  season: SeasonOverview;
  lines: Line[];
  domain: [number, number];
  format: (value: number) => string;
  unit: (value: number) => string;
  initial?: string[];
}) {
  const start = initial ?? leaders(lines);
  const [highlight, setHighlight] = useState<string[]>(start);
  const [at, setAt] = useState<number | null>(null);
  const count = season.rounds.length;
  const x = scale([0, Math.max(1, count - 1)], [M.left, W - M.right]);
  const y = scale(domain, [M.top, H - M.bottom]);
  const shown = new Set(highlight);
  const drawn = lines
    .map((line) => ({
      line,
      points: line.values.flatMap((value, index) => (value === null ? [] : [{ lap: index, value }])),
      highlighted: shown.has(line.code),
    }))
    .toSorted((a, b) => Number(a.highlighted) - Number(b.highlighted));
  // A domain from high to low (points) or low to high (gaps): clamp a value into it either way.
  const [low, high] = domain[0] < domain[1] ? domain : [domain[1], domain[0]];
  const clamp = (value: number) => Math.min(Math.max(value, low), high);
  const ends = drawn.flatMap(({ line, points: found, highlighted }) => {
    const end = highlighted ? found.at(-1) : undefined;
    return end ? [{ line, x: x(end.lap) + 6, y: y(clamp(end.value)) }] : [];
  });
  const heights = spread(
    ends.map((end) => end.y),
    12,
    [M.top, H - M.bottom],
  );
  const round = at === null ? null : season.rounds[at];
  const toggle = (code: string) =>
    setHighlight((codes) => (codes.includes(code) ? codes.filter((c) => c !== code) : [...codes, code]));
  const pick = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const position = ((event.clientX - box.left) / box.width) * W;
    const index = Math.round(((position - M.left) / (W - M.left - M.right)) * Math.max(1, count - 1));
    setAt(Math.min(count - 1, Math.max(0, index)));
  };
  const keys = (event: KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1 };
    const move = moves[event.key];
    if (move !== undefined) setAt(Math.min(count - 1, Math.max(0, (at ?? -1) + move)));
    else if (event.key === "Home") setAt(0);
    else if (event.key === "End") setAt(count - 1);
    else if (event.key === "Escape") setAt(null);
    else return;
    event.preventDefault();
  };
  const readout = drawn
    .filter((one) => one.highlighted)
    .map(({ line }) => ({ line, value: at === null ? null : (line.values[at] ?? null) }))
    .filter((one) => one.value !== null)
    .toSorted((a, b) => ((a.value ?? 0) - (b.value ?? 0)) * (domain[0] > domain[1] ? -1 : 1));

  return (
    <div className="flex flex-col gap-3">
      <fieldset className="flex flex-wrap gap-2">
        <legend className="sr-only">{t.highlighted}</legend>
        {lines.map((line) => (
          <button
            key={line.code}
            type="button"
            aria-pressed={shown.has(line.code)}
            title={line.label}
            onClick={() => toggle(line.code)}
            style={teamStyle(line.colour)}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-semibold text-xs transition-colors",
              shown.has(line.code)
                ? "border-[var(--team)] bg-surface-raised text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <span
              className={cn("h-3 w-1 rounded-full bg-[var(--team)]", !shown.has(line.code) && "opacity-40")}
              aria-hidden
            />
            {line.code.length <= 3 ? line.code : line.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setHighlight(start)}
          className="rounded-full px-2.5 py-1 font-semibold text-primary-text text-xs hover:underline"
        >
          {t.top}
        </button>
        <button
          type="button"
          onClick={() => setHighlight(lines.map((line) => line.code))}
          className="rounded-full px-2.5 py-1 font-semibold text-primary-text text-xs hover:underline"
        >
          {t.all}
        </button>
      </fieldset>
      <p role="status" className="figures min-h-5 text-muted-foreground text-sm">
        {round &&
          `${t.afterRound(round.round, round.grand_prix)} · ${readout
            .map(({ line, value }) => `${line.code.length <= 3 ? line.code : line.label} ${unit(value ?? 0)}`)
            .join(" · ")}`}
      </p>
      <Panel min="40rem" className="py-3">
        <div
          role="slider"
          aria-label={label}
          aria-valuemin={1}
          aria-valuemax={count}
          aria-valuenow={(at ?? 0) + 1}
          aria-valuetext={round ? `${t.round} ${round.round}` : `${t.round} ${season.rounds[0]?.round ?? 1}`}
          tabIndex={0}
          onKeyDown={keys}
          className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <svg
            viewBox={`0 0 ${W} ${H}`}
            aria-hidden
            className="block h-auto w-full select-none"
            onPointerMove={pick}
            onPointerDown={pick}
            onPointerLeave={() => setAt(null)}
          >
            {ticks([low, high]).map((tick) => (
              <g key={tick} className="text-muted-foreground">
                <line
                  x1={M.left}
                  x2={W - M.right}
                  y1={y(tick)}
                  y2={y(tick)}
                  stroke="currentColor"
                  strokeOpacity={0.12}
                />
                <text x={M.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" fill="currentColor" fontSize={11}>
                  {format(tick)}
                </text>
              </g>
            ))}
            {season.rounds.map((one, index) => (
              <text
                key={one.round}
                x={x(index)}
                y={H - 8}
                textAnchor="middle"
                fontSize={11}
                className="fill-muted-foreground"
              >
                {one.round}
              </text>
            ))}
            {drawn.map(({ line, points: found, highlighted }) => (
              <g key={line.code} style={teamStyle(line.colour)} data-line={line.code}>
                <path
                  d={path(
                    found.map((point) => ({ ...point, value: clamp(point.value) })),
                    x,
                    y,
                  )}
                  fill="none"
                  stroke={highlighted ? "var(--team)" : "var(--muted-foreground)"}
                  strokeOpacity={highlighted ? 1 : 0.18}
                  strokeWidth={highlighted ? 2.25 : 1.25}
                  strokeLinejoin="round"
                  pathLength={highlighted ? 1 : undefined}
                  className={highlighted ? "draw" : undefined}
                />
              </g>
            ))}
            {ends.map((end, index) => (
              <text
                key={end.line.code}
                data-label={end.line.code}
                x={end.x}
                y={heights[index]}
                dy="0.32em"
                fontSize={11}
                fontWeight={700}
                style={teamStyle(end.line.colour)}
                fill="var(--team)"
              >
                {end.line.code.length <= 3 ? end.line.code : end.line.label}
              </text>
            ))}
            {at !== null && (
              <line
                x1={x(at)}
                x2={x(at)}
                y1={M.top}
                y2={H - M.bottom}
                className="stroke-foreground"
                strokeOpacity={0.5}
              />
            )}
          </svg>
        </div>
      </Panel>
    </div>
  );
}
