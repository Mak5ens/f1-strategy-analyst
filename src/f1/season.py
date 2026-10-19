"""A season told by its numbers (LAB-215): the championship round by round, the drivers' form, and the teams' pace.
Every number is read or computed by code from the lake, never by a model.

- **Championship**: the points of the races and sprints, added round by round from the results, so that they add
  up to the championship's; the order after each round is by points, then by wins, then by second places and so on
  (the count-back of the sporting regulations).
- **Form**: the points scored in the last `FORM_ROUNDS` rounds raced.
- **Qualifying pace**: each team's best lap of the qualifying (any part) less the best lap of all, in % of it. A team
  out in Q1 never ran on the track of Q3: the gap counts that too.
- **Race pace**: on each lap of the race, each team's median time over its cars' clean laps (`is_clean`); its gap
  that lap to the fastest team, in %; the team's gap for the race is the median of those, less the best team's, so
  that the fastest team is at 0. Under `MIN_PACE_LAPS` laps, no gap: too few laps say nothing.
"""

import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import Field

from f1.display import Driver, Response, driver, grand_prix_fr, team_colour
from f1.tools.data import RaceData, integer, is_clean, number

FORM_ROUNDS = 5
MIN_PACE_LAPS = 10
QUALIFYING = ("q1_s", "q2_s", "q3_s")


class SeasonRound(Response):
    round: int
    grand_prix: str = Field(description="In French")
    sprint: bool = Field(description="A sprint was raced that weekend")


class RoundResult(Response):
    text: str = Field(description="The place, or R retired, D disqualified, W withdrawn...")
    position: int | None = None
    grid: int | None = None
    points: float = Field(description="Race and sprint of the weekend")


class DriverSeason(Response):
    driver: Driver
    position: int = Field(description="In the championship after the last round")
    points: float
    wins: int
    form_points: float = Field(description="Points of the last rounds raced (`form_rounds`)")
    cumulative: list[float] = Field(description="Points after each round, in the order of `rounds`")
    positions: list[int] = Field(description="Place in the championship after each round")
    results: list[RoundResult | None] = Field(description="Each round's result; None when not raced")


class TeamSeason(Response):
    team: str
    colour: str | None = None
    position: int
    points: float
    wins: int
    cumulative: list[float]
    positions: list[int]
    qualifying_gap_pct: list[float | None] = Field(description="Best qualifying lap's gap to the best of all, in %")
    race_gap_pct: list[float | None] = Field(description="Median race lap gap to the fastest team, in %")


class SeasonOverview(Response):
    season: int
    rounds: list[SeasonRound] = Field(description="The rounds raced, in order")
    form_rounds: int
    drivers: list[DriverSeason] = Field(description="In championship order")
    teams: list[TeamSeason] = Field(description="In championship order")


def overview(data: RaceData, season: int) -> SeasonOverview | None:
    """The season so far; None when no round of it has been raced."""
    results = data.season_results(season, ["Q", "S", "R"])
    raced = sorted({int(row["round"]) for row in results if row["session"] == "R"})
    if not raced:
        return None
    events = {int(row["round"]): str(row["event_name"]) for row in data.events(season)}
    sprints = {int(row["round"]) for row in results if row["session"] == "S"}
    rounds = [
        SeasonRound(round=number_, grand_prix=grand_prix_fr(events.get(number_, "")), sprint=number_ in sprints)
        for number_ in raced
    ]
    races = [row for row in results if row["session"] == "R"]
    names = {str(row["driver"]): driver(row["driver"], row.get("full_name"), _text(row.get("team"))) for row in races}
    laps = data.season_laps(season, sorted(names))
    return SeasonOverview(
        season=season,
        rounds=rounds,
        form_rounds=FORM_ROUNDS,
        drivers=drivers_season(results, raced, names),
        teams=teams_season(results, laps, raced),
    )


def drivers_season(
    results: Sequence[Mapping[str, Any]], raced: Sequence[int], names: Mapping[str, Driver]
) -> list[DriverSeason]:
    scored = _scored(results, raced, key="driver")
    order, cumulative, positions = standings(scored, raced)
    by_round = {(int(row["round"]), str(row["driver"])): row for row in results if row["session"] == "R"}
    found = []
    for code in order:
        per_round = scored[code]
        found.append(
            DriverSeason(
                driver=names[code],
                position=positions[code][-1],
                points=cumulative[code][-1],
                wins=_wins(per_round),
                form_points=round(sum(per_round.get(number_, (0.0, ()))[0] for number_ in raced[-FORM_ROUNDS:]), 1),
                cumulative=cumulative[code],
                positions=positions[code],
                results=[_result(by_round.get((number_, code)), per_round.get(number_)) for number_ in raced],
            )
        )
    return found


def teams_season(
    results: Sequence[Mapping[str, Any]], laps: Sequence[Mapping[str, Any]], raced: Sequence[int]
) -> list[TeamSeason]:
    scored = _scored(results, raced, key="team")
    order, cumulative, positions = standings(scored, raced)
    qualifying = {number_: qualifying_gaps(results, number_) for number_ in raced}
    teams = {(int(row["round"]), str(row["driver"])): _text(row.get("team")) for row in results}
    race = {number_: race_gaps(laps, teams, number_) for number_ in raced}
    return [
        TeamSeason(
            team=team,
            colour=team_colour(team),
            position=positions[team][-1],
            points=cumulative[team][-1],
            wins=_wins(scored[team]),
            cumulative=cumulative[team],
            positions=positions[team],
            qualifying_gap_pct=[qualifying[number_].get(team) for number_ in raced],
            race_gap_pct=[race[number_].get(team) for number_ in raced],
        )
        for team in order
    ]


def _scored(
    results: Iterable[Mapping[str, Any]], raced: Sequence[int], *, key: str
) -> dict[str, dict[int, tuple[float, tuple[int, ...]]]]:
    """Per driver (or team) and round: the points of the race and sprint, and the race places classified."""
    scored: dict[str, dict[int, tuple[float, tuple[int, ...]]]] = defaultdict(dict)
    for row in results:
        if row["session"] not in ("R", "S") or int(row["round"]) not in raced or not row.get(key):
            continue
        name, number_ = str(row[key]), int(row["round"])
        points, places = scored[name].get(number_, (0.0, ()))
        points += number(row["points"]) or 0.0
        if row["session"] == "R" and _classified(row) and (position := integer(row["position"])) is not None:
            places = (*places, position)
        scored[name][number_] = (points, places)
    return scored


def standings(
    scored: Mapping[str, Mapping[int, tuple[float, tuple[int, ...]]]], raced: Sequence[int]
) -> tuple[list[str], dict[str, list[float]], dict[str, list[int]]]:
    """The order after the last round, and each one's points and place after every round: by points, then by the
    count-back of race places (wins, then second places...)."""
    cumulative: dict[str, list[float]] = {name: [] for name in scored}
    positions: dict[str, list[int]] = {name: [] for name in scored}
    places: dict[str, list[int]] = {name: [0] * 30 for name in scored}
    total = dict.fromkeys(scored, 0.0)
    order: list[str] = []
    for number_ in raced:
        for name, per_round in scored.items():
            points, found = per_round.get(number_, (0.0, ()))
            total[name] += points
            for place in found:
                if place <= len(places[name]):
                    places[name][place - 1] += 1
            cumulative[name].append(round(total[name], 1))
        order = sorted(scored, key=lambda name: (-total[name], [-count for count in places[name]], name))
        for rank, name in enumerate(order, start=1):
            positions[name].append(rank)
    return order, cumulative, positions


def qualifying_gaps(results: Iterable[Mapping[str, Any]], round_number: int) -> dict[str, float]:
    """Each team's best qualifying lap less the best of all, in % of it."""
    best: dict[str, float] = {}
    for row in results:
        if row["session"] != "Q" or int(row["round"]) != round_number or not (team := _text(row.get("team"))):
            continue
        times = [time for part in QUALIFYING if (time := number(row.get(part))) is not None]
        if times:
            best[team] = min(best.get(team, min(times)), min(times))
    if not best:
        return {}
    pole = min(best.values())
    return {team: round((time - pole) / pole * 100, 3) for team, time in best.items()}


def race_gaps(
    laps: Iterable[Mapping[str, Any]], teams: Mapping[tuple[int, str], str | None], round_number: int
) -> dict[str, float]:
    """Each team's median gap, lap by lap, to the fastest team on the clean laps of a race, in %; the fastest at 0."""
    by_lap: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for lap in laps:
        if int(lap["round"]) != round_number or not is_clean(dict(lap)):
            continue
        if team := teams.get((round_number, str(lap["driver"]))):
            by_lap[int(lap["lap_number"])][team].append(float(lap["lap_time_s"]))
    gaps: dict[str, list[float]] = defaultdict(list)
    for at in by_lap.values():
        if len(at) < 2:
            continue
        times = {team: statistics.median(values) for team, values in at.items()}
        fastest = min(times.values())
        for team, time in times.items():
            gaps[team].append((time - fastest) / fastest * 100)
    medians = {team: statistics.median(values) for team, values in gaps.items() if len(values) >= MIN_PACE_LAPS}
    if not medians:
        return {}
    best = min(medians.values())
    return {team: round(value - best, 3) for team, value in medians.items()}


def _wins(per_round: Mapping[int, tuple[float, tuple[int, ...]]]) -> int:
    return sum(places.count(1) for _, places in per_round.values())


def _result(row: Mapping[str, Any] | None, scored: tuple[float, tuple[int, ...]] | None) -> RoundResult | None:
    if row is None:
        return None
    text = str(row.get("classified_position") or "")
    return RoundResult(
        text=text,
        position=integer(row["position"]) if _classified(row) else None,
        grid=integer(row.get("grid_position")),
        points=round(scored[0], 1) if scored else 0.0,
    )


def _classified(row: Mapping[str, Any]) -> bool:
    return str(row.get("classified_position") or "").isdigit()


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
