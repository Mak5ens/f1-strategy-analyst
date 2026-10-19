"""Two drivers face to face over a season (LAB-212): qualifying, race and pace, each measured by code in the lake.

Every gap is the first driver's time less the second's: positive, the first driver was slower.

- **Qualifying**: the best laps of the last part both drivers reached (Q3, else Q2, else Q1), as the results give
  them. The one ahead is the one with the better place in the session. When the results have the places but not
  the times (Miami 2025), the places count and the gap is left empty.
- **Race**: the places at the end of the race (`position`, every driver started, classified or not), and the points
  of the weekend, sprints included, so that they add up to the championship's. A race neither finished classified
  (both retired, both disqualified) counts for nobody: their order says nothing.
- **Pace**: the median gap on the laps both drivers covered clean, the same lap of the same race (`is_clean`, as the
  tools read a lap: not lap 1, no stop, green flag all lap, not deleted). Under 5 such laps, no pace: too few laps
  say nothing.

A round a driver did not race has no gap there, rather than a gap made up.
"""

import statistics
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import Field

from f1.display import Driver, Response, driver, grand_prix_fr
from f1.tools.data import RaceData, integer, is_clean, number

MIN_PACE_LAPS = 5
PARTS = ("q3_s", "q2_s", "q1_s")


class DuelQualifying(Response):
    part: Literal["Q1", "Q2", "Q3"] | None = Field(None, description="The last part both reached; None, no times")
    first_s: float | None = None
    second_s: float | None = None
    gap_s: float | None = Field(None, description="First driver's time less the second's: positive, the first slower")
    first_position: int | None = None
    second_position: int | None = None


class DuelRace(Response):
    first_position: int | None = None
    second_position: int | None = None
    first_text: str = Field(description="A place, or R retired, D disqualified...")
    second_text: str
    first_points: float = Field(description="Race and sprint of the weekend")
    second_points: float


class DuelPace(Response):
    laps: int = Field(description="Laps both covered clean, the same lap")
    gap_s: float = Field(description="Median of the first driver's lap time less the second's on those laps")


class DuelRound(Response):
    round: int
    grand_prix: str = Field(description="In French")
    qualifying: DuelQualifying | None = None
    race: DuelRace | None = None
    pace: DuelPace | None = None


class DuelSummary(Response):
    qualifying_first: int = Field(description="Qualifying sessions the first driver was ahead in")
    qualifying_second: int
    race_first: int = Field(description="Races the first driver finished ahead in")
    race_second: int
    points_first: float = Field(description="Races and sprints")
    points_second: float
    qualifying_gap_s: float | None = Field(None, description="Median of the qualifying gaps")
    pace_gap_s: float | None = Field(None, description="Median of the races' pace gaps")


class Duel(Response):
    season: int
    first: Driver
    second: Driver
    rounds: list[DuelRound] = Field(default_factory=list, description="The rounds raced, in order")
    summary: DuelSummary


def duel(data: RaceData, season: int, first: str, second: str) -> Duel | None:
    """The duel of two drivers over a season; None when either did not race in it."""
    results = data.season_results(season, ["Q", "S", "R"])
    by: dict[tuple[int, str, str], Mapping[str, Any]] = {
        (int(row["round"]), str(row["session"]), str(row["driver"])): row for row in results
    }
    raced = sorted({key[0] for key in by if key[1] == "R"})
    names = _drivers(results)
    if first not in names or second not in names or first == second:
        return None
    laps = _laps(data.season_laps(season, [first, second]))
    events = {int(row["round"]): str(row["event_name"]) for row in data.events(season)}

    rounds = []
    for number_ in raced:
        rounds.append(
            DuelRound(
                round=number_,
                grand_prix=grand_prix_fr(events.get(number_, "")),
                qualifying=qualifying_gap(by.get((number_, "Q", first)), by.get((number_, "Q", second))),
                race=_race(by, number_, first, second),
                pace=pace_gap(laps.get((number_, first), {}), laps.get((number_, second), {})),
            )
        )
    return Duel(season=season, first=names[first], second=names[second], rounds=rounds, summary=summarize(rounds))


def _drivers(results: Iterable[Mapping[str, Any]]) -> dict[str, Driver]:
    """Each driver of the season, with the team of their last race."""
    found: dict[str, Driver] = {}
    for row in results:
        if row["session"] == "R":
            found[str(row["driver"])] = driver(row["driver"], row.get("full_name"), _text(row.get("team")))
    return found


def qualifying_gap(mine: Mapping[str, Any] | None, theirs: Mapping[str, Any] | None) -> DuelQualifying | None:
    if mine is None or theirs is None:
        return None
    for part in PARTS:
        a, b = number(mine.get(part)), number(theirs.get(part))
        if a is not None and b is not None:
            return DuelQualifying(
                part=part[:2].upper(),
                first_s=a,
                second_s=b,
                gap_s=round(a - b, 3),
                first_position=_position(mine),
                second_position=_position(theirs),
            )
    if _position(mine) is None or _position(theirs) is None:
        return None
    return DuelQualifying(first_position=_position(mine), second_position=_position(theirs))


def _race(
    by: Mapping[tuple[int, str, str], Mapping[str, Any]], round_: int, first: str, second: str
) -> DuelRace | None:
    mine, theirs = by.get((round_, "R", first)), by.get((round_, "R", second))
    if mine is None or theirs is None:
        return None

    def points(code: str) -> float:
        return sum(number(row["points"]) or 0.0 for s in ("R", "S") if (row := by.get((round_, s, code))))

    return DuelRace(
        first_position=integer(mine["position"]),
        second_position=integer(theirs["position"]),
        first_text=_text(mine.get("classified_position")) or str(integer(mine["position"]) or ""),
        second_text=_text(theirs.get("classified_position")) or str(integer(theirs["position"]) or ""),
        first_points=points(first),
        second_points=points(second),
    )


def _laps(rows: Iterable[dict[str, Any]]) -> dict[tuple[int, str], dict[int, dict[str, Any]]]:
    laps: dict[tuple[int, str], dict[int, dict[str, Any]]] = {}
    for row in rows:
        laps.setdefault((int(row["round"]), str(row["driver"])), {})[int(row["lap_number"])] = row
    return laps


def pace_gap(mine: Mapping[int, dict[str, Any]], theirs: Mapping[int, dict[str, Any]]) -> DuelPace | None:
    """The median gap on the laps both covered clean; None under `MIN_PACE_LAPS` of them."""
    gaps = [
        float(mine[lap]["lap_time_s"]) - float(theirs[lap]["lap_time_s"])
        for lap in sorted(mine.keys() & theirs.keys())
        if is_clean(mine[lap]) and is_clean(theirs[lap])
    ]
    if len(gaps) < MIN_PACE_LAPS:
        return None
    return DuelPace(laps=len(gaps), gap_s=round(statistics.median(gaps), 3))


def summarize(rounds: list[DuelRound]) -> DuelSummary:
    qualifying = [r.qualifying for r in rounds if r.qualifying]
    races = [r.race for r in rounds if r.race]
    paces = [r.pace.gap_s for r in rounds if r.pace]

    def ahead(pairs: Iterable[tuple[int | None, int | None]]) -> tuple[int, int]:
        ranked = [(a, b) for a, b in pairs if a is not None and b is not None and a != b]
        return sum(a < b for a, b in ranked), sum(b < a for a, b in ranked)

    qualifying_first, qualifying_second = ahead((q.first_position, q.second_position) for q in qualifying)
    race_first, race_second = ahead(
        (r.first_position, r.second_position) for r in races if r.first_text.isdigit() or r.second_text.isdigit()
    )
    timed = [q.gap_s for q in qualifying if q.gap_s is not None]
    return DuelSummary(
        qualifying_first=qualifying_first,
        qualifying_second=qualifying_second,
        race_first=race_first,
        race_second=race_second,
        points_first=sum(r.first_points for r in races),
        points_second=sum(r.second_points for r in races),
        qualifying_gap_s=round(statistics.median(timed), 3) if timed else None,
        pace_gap_s=round(statistics.median(paces), 3) if paces else None,
    )


def _position(row: Mapping[str, Any]) -> int | None:
    """The place in the session: `position`, or the classified place when the results leave it empty."""
    if (position := integer(row["position"])) is not None:
        return position
    text = _text(row.get("classified_position"))
    return int(text) if text and text.isdigit() else None


def _text(value: Any) -> str | None:
    return None if value is None or (isinstance(value, float) and value != value) else str(value)


def season_drivers(data: RaceData, season: int) -> list[Driver]:
    """The drivers who raced in a season, most points first (races and sprints), with the team of their last race."""
    results = data.season_results(season, ["S", "R"])
    points: dict[str, float] = {}
    for row in results:
        points[str(row["driver"])] = points.get(str(row["driver"]), 0.0) + (number(row["points"]) or 0.0)
    drivers = _drivers(results)
    return [drivers[code] for code in sorted(drivers, key=lambda code: -points.get(code, 0.0))]
