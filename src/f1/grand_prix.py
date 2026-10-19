"""What the site shows of a Grand Prix, read from the lake: the calendar of a season and the page of a race (LAB-202).

The race is the site's entry point: its page says what happened (classification, grid, strategies, stops,
neutralizations, penalties, standings after the round, weather) before any debrief. Everything here is read or
computed by code, with the analysis tools' own functions: a race page never calls a model.
"""

import statistics
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Literal

import duckdb
import pandas as pd
from pydantic import Field

from core.tools import ToolError
from f1.display import Driver, Response, driver, grand_prix_fr
from f1.tools.data import RaceData, SessionRef, integer, number
from f1.tools.neutralizations import Kind, find_periods
from f1.tools.penalties import penalties, reason_fr
from f1.tools.pit_loss import stop_loss


class RaceSummary(Response):
    season: int
    round: int
    grand_prix: str = Field(description="In French")
    event: str = Field(description="The official name in English, as the data names it")
    location: str | None = None
    country: str | None = None
    date: datetime | None = Field(None, description="Start of the race, UTC")
    sprint: bool = Field(False, description="A sprint weekend")
    winner: Driver | None = Field(None, description="None until the race has results")


class Classified(Response):
    position: int | None = Field(None, description="Finishing order, also for drivers not classified")
    position_text: str = Field(description="A number, or R retired, D disqualified, W withdrawn, N not classified")
    driver: Driver
    number: str | None = None
    grid: int | None = Field(None, description="Starting position; 0 for a pit lane start")
    places_gained: int | None = Field(None, description="Grid minus finish: positive when the driver gained places")
    laps: int | None = None
    time_s: float | None = Field(None, description="Race time, the winner only")
    gap_s: float | None = Field(None, description="Gap to the winner, finishers on the lead lap only")
    laps_behind: int | None = Field(None, description="Laps down on the winner, finishers lapped only")
    status: str | None = None
    points: float = 0


class BestLap(Response):
    driver: Driver
    lap: int
    lap_time_s: float
    gap_s: float = Field(description="Behind the fastest lap of the race")


class Stint(Response):
    stint: int
    compound: str | None = Field(None, description="SOFT, MEDIUM, HARD, INTERMEDIATE or WET")
    start_lap: int
    end_lap: int
    laps: int
    fresh: bool | None = Field(None, description="A new set, rather than one used in an earlier session")


class Stop(Response):
    stop_number: int
    lap: int = Field(description="In-lap")
    pit_lane_time_s: float | None = None
    stationary_time_s: float | None = None
    time_lost_s: float | None = Field(None, description="What the stop cost against two normal laps (pit_stop_loss)")
    compound_after: str | None = None
    neutralized: bool = Field(False, description="Under safety car, VSC or red flag: the stop cost less")


class Strategy(Response):
    driver: Driver
    stints: list[Stint] = Field(default_factory=list)
    stops: list[Stop] = Field(default_factory=list)


class Neutralization(Response):
    kind: Kind
    start_lap: int
    end_lap: int
    duration_s: float


class Penalty(Response):
    driver: Driver
    kind: Literal["time", "drive_through", "stop_go"]
    seconds: int | None = None
    reason: str = Field(description="In French")
    lap: int = Field(description="Lap race control announced it")


class DriverStanding(Response):
    position: int | None = None
    driver: Driver
    points: float
    wins: int
    change: int | None = Field(None, description="Places gained in the championship with this round")


class TeamStanding(Response):
    position: int | None = None
    team: str
    colour: str | None = None
    points: float
    wins: int
    change: int | None = Field(None, description="Places gained in the championship with this round")


class Weather(Response):
    air_temp_min_c: float = Field(description="Lowest during the race")
    air_temp_max_c: float
    track_temp_min_c: float
    track_temp_max_c: float
    humidity_pct: float = Field(description="Average")
    rainfall: bool = Field(description="Rain at some point of the race")


class Race(Response):
    """A Grand Prix as its page shows it. A section without data is empty, never filled with a guess."""

    summary: RaceSummary
    total_laps: int | None = None
    classification: list[Classified] = Field(default_factory=list)
    fastest_lap: BestLap | None = None
    best_laps: list[BestLap] = Field(default_factory=list, description="Each driver's best lap, fastest first")
    strategies: list[Strategy] = Field(default_factory=list, description="In finishing order")
    neutralizations: list[Neutralization] = Field(default_factory=list)
    penalties: list[Penalty] = Field(default_factory=list)
    driver_standings: list[DriverStanding] = Field(default_factory=list, description="After this round")
    team_standings: list[TeamStanding] = Field(default_factory=list, description="After this round")
    weather: Weather | None = None


class Lap(Response):
    lap: int
    position: int | None = Field(None, description="At the end of the lap")
    gap_s: float | None = Field(
        None, description="Behind the leader at the line, the end of this lap: the race's gap, as `gaps` computes it"
    )
    lap_time_s: float | None = None
    compound: str | None = None
    tyre_age: int | None = Field(None, description="Laps on this set, this lap included, earlier sessions too")
    pit: Literal["in", "out"] | None = Field(None, description="The in-lap or the out-lap of a stop")


class DriverLaps(Response):
    driver: Driver
    grid: int | None = Field(None, description="Starting position, the chart's lap 0; 0 for a pit lane start")
    laps: list[Lap] = Field(default_factory=list)


class RaceLaps(Response):
    """A race lap by lap, for its charts (LAB-189): read from the lake, as the tools read it, never by a model."""

    season: int
    round: int
    total_laps: int | None = None
    drivers: list[DriverLaps] = Field(default_factory=list, description="In finishing order")
    neutralizations: list[Neutralization] = Field(default_factory=list)


class GrandPrix:
    """The races of the lake. Each query runs on its own cursor, as the tools' (`RaceData`).

    A race with results does not change: its page is computed once (about a second from S3) and kept.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._db = connection
        self._data = RaceData(connection)
        self._raced: dict[tuple[int, int], Race] = {}
        self._lapped: dict[tuple[int, int], RaceLaps] = {}

    def seasons(self) -> list[int]:
        """The seasons with at least one race in the lake, the latest first."""
        rows = self._query("SELECT DISTINCT season FROM sessions WHERE session = 'R' ORDER BY season DESC")
        return [int(row["season"]) for row in rows]

    def people(self) -> tuple[list[str], list[str]]:
        """The names of every driver and team of the lake, as the results write them: what a question may name."""
        rows = self._query("SELECT DISTINCT full_name, team FROM results", table="results")
        drivers = sorted({name for row in rows if (name := _text(row["full_name"])) and name != "None None"})
        return drivers, sorted({team for row in rows if (team := _text(row["team"]))})

    def calendar(self, season: int) -> list[RaceSummary]:
        """The rounds of a season in the lake, in order, with their winner once the race has results."""
        rows = self._query(
            "SELECT round, any_value(event_name) AS event, any_value(location) AS location, "
            "any_value(country) AS country, max(start_utc) FILTER (session = 'R') AS date, "
            "bool_or(session = 'S') AS sprint FROM sessions WHERE season = ? GROUP BY round ORDER BY round",
            [season],
        )
        winners = {
            int(row["round"]): driver(row["driver"], row["full_name"], _text(row["team"]))
            for row in self._query(
                "SELECT round, driver, full_name, team FROM results WHERE season = ? AND session = 'R' "
                "AND position = 1",
                [season],
                table="results",
            )
        }
        return [_summary(season, row, winners.get(int(row["round"]))) for row in rows]

    def latest(self) -> RaceSummary | None:
        """The last race with results."""
        rows = self._query(
            "SELECT season, round FROM results WHERE session = 'R' AND position = 1 "
            "ORDER BY season DESC, round DESC LIMIT 1",
            table="results",
        )
        return self.summary(int(rows[0]["season"]), int(rows[0]["round"])) if rows else None

    def featured(self, with_debriefs: Iterable[tuple[int, int]], count: int = 4) -> list[RaceSummary]:
        """The races the home page puts forward: the last one raced, then the latest that have a debrief, then the
        rounds before the last one."""
        latest = self.latest()
        if latest is None:
            return []
        keys = [(latest.season, latest.round), *sorted(set(with_debriefs), reverse=True)]
        keys += [(latest.season, number) for number in range(latest.round - 1, 0, -1)]
        races: list[RaceSummary] = []
        for season, round_number in dict.fromkeys(keys):
            if len(races) == count:
                break
            if (race := self.summary(season, round_number)) and race.winner:
                races.append(race)
        return races

    def summary(self, season: int, round_number: int) -> RaceSummary | None:
        return next((race for race in self.calendar(season) if race.round == round_number), None)

    def race(self, season: int, round_number: int) -> Race | None:
        """The page of a race; None when the lake has no session of that round."""
        if (season, round_number) in self._raced:
            return self._raced[season, round_number]
        summary = self.summary(season, round_number)
        if summary is None:
            return None
        race = self._race(summary)
        if summary.winner:
            self._raced[season, round_number] = race
        return race

    def laps(self, season: int, round_number: int) -> RaceLaps | None:
        """Every lap of every driver of a race; None when it has no results yet. Kept, as a race's page is."""
        if (season, round_number) in self._lapped:
            return self._lapped[season, round_number]
        race = self.race(season, round_number)
        if race is None or not race.summary.winner:
            return None
        ref = SessionRef(season=season, round=round_number)
        laps = [lap for lap in self._rows(lambda: self._data.laps(ref)) if not lap.get("fastf1_generated")]
        lapped = RaceLaps(
            season=season,
            round=round_number,
            total_laps=race.total_laps,
            drivers=_driver_laps(race, laps),
            neutralizations=race.neutralizations,
        )
        self._lapped[season, round_number] = lapped
        return lapped

    def _race(self, summary: RaceSummary) -> Race:
        season, round_number = summary.season, summary.round
        ref = SessionRef(season=season, round=round_number)
        results = self._data.results(season, round_number, "R") if summary.winner else []
        drivers = {str(row["driver"]): driver(row["driver"], row["full_name"], _text(row["team"])) for row in results}
        laps = self._rows(lambda: self._data.laps(ref))
        best_laps = _best_laps(laps, drivers)
        totals = self._query(
            "SELECT total_laps FROM sessions WHERE season = ? AND round = ? AND session = 'R'", [season, round_number]
        )
        messages = self._rows(lambda: self._data.race_control_messages(ref))
        return Race(
            summary=summary,
            total_laps=integer(totals[0]["total_laps"]) if totals else None,
            classification=_classification(results, drivers),
            fastest_lap=best_laps[0] if best_laps else None,
            best_laps=best_laps,
            strategies=self._strategies(ref, results, drivers, laps),
            neutralizations=[
                Neutralization(kind=p.kind, start_lap=p.start_lap, end_lap=p.end_lap, duration_s=p.duration_s)
                for p in (find_periods(messages) if messages else [])
            ],
            penalties=[
                Penalty(
                    driver=drivers.get(penalty.driver) or driver(penalty.driver, None, None),
                    kind=penalty.kind,
                    seconds=penalty.seconds,
                    reason=reason_fr(penalty.reason),
                    lap=penalty.lap,
                )
                for penalty in penalties(messages)[0]
            ],
            driver_standings=self._driver_standings(season, round_number),
            team_standings=self._team_standings(season, round_number),
            weather=self._weather(ref),
        )

    def _strategies(
        self, ref: SessionRef, results: list[dict[str, Any]], drivers: dict[str, Driver], laps: list[dict[str, Any]]
    ) -> list[Strategy]:
        stints = self._query(
            "SELECT * FROM stints WHERE season = ? AND round = ? AND session = 'R' ORDER BY driver, stint",
            [ref.season, ref.round],
            table="stints",
        )
        stops = self._query(
            "SELECT * FROM pit_stops WHERE season = ? AND round = ? AND session = 'R' ORDER BY driver, stop_number",
            [ref.season, ref.round],
            table="pit_stops",
        )
        laps_of: dict[str, dict[int, dict[str, Any]]] = {}
        for lap in laps:
            laps_of.setdefault(str(lap["driver"]), {})[int(lap["lap_number"])] = lap
        order = [str(row["driver"]) for row in results] or sorted({str(row["driver"]) for row in stints})
        strategies = []
        for code in order:
            mine = [row for row in stints if row["driver"] == code and integer(row["start_lap"]) is not None]
            if not mine:
                continue
            strategies.append(
                Strategy(
                    driver=drivers.get(code) or driver(code, None, _text(mine[0]["team"])),
                    stints=[
                        Stint(
                            stint=int(row["stint"]),
                            compound=_text(row["compound"]),
                            start_lap=int(row["start_lap"]),
                            end_lap=int(row["end_lap"]),
                            laps=int(row["laps"]),
                            fresh=None if _text(row["fresh_tyre"]) is None else bool(row["fresh_tyre"]),
                        )
                        for row in mine
                    ],
                    stops=[_stop(laps_of.get(code, {}), stop) for stop in stops if stop["driver"] == code],
                )
            )
        return strategies

    def _driver_standings(self, season: int, round_number: int) -> list[DriverStanding]:
        rows = self._query(
            "SELECT * FROM driver_standings WHERE season = ? AND round = ? ORDER BY position NULLS LAST",
            [season, round_number],
            table="driver_standings",
        )
        before = {
            str(row["driver_id"]): integer(row["position"])
            for row in self._query(
                "SELECT driver_id, position FROM driver_standings WHERE season = ? AND round = ?",
                [season, round_number - 1],
                table="driver_standings",
            )
        }
        # Name and team of each driver as of this round: from the last race they started up to it.
        entries = {
            str(row["driver_id"]): row
            for row in self._query(
                "SELECT driver_id, driver, full_name, team FROM results WHERE season = ? AND round <= ? "
                "AND session = 'R' ORDER BY round",
                [season, round_number],
                table="results",
            )
        }
        standings = []
        for row in rows:
            entry = entries.get(str(row["driver_id"]), {})
            standings.append(
                DriverStanding(
                    position=integer(row["position"]),
                    driver=driver(
                        str(row["driver"] or entry.get("driver") or row["driver_id"]),
                        _text(entry.get("full_name")),
                        _text(entry.get("team")),
                    ),
                    points=number(row["points"]) or 0,
                    wins=integer(row["wins"]) or 0,
                    change=_change(before.get(str(row["driver_id"])), integer(row["position"])),
                )
            )
        return standings

    def _team_standings(self, season: int, round_number: int) -> list[TeamStanding]:
        rows = self._query(
            "SELECT * FROM constructor_standings WHERE season = ? AND round = ? ORDER BY position NULLS LAST",
            [season, round_number],
            table="constructor_standings",
        )
        before = {
            str(row["constructor_id"]): integer(row["position"])
            for row in self._query(
                "SELECT constructor_id, position FROM constructor_standings WHERE season = ? AND round = ?",
                [season, round_number - 1],
                table="constructor_standings",
            )
        }
        # The teams' names as the results give them, the names the colours are known by ("Red Bull Racing").
        names = {
            str(row["team_id"]): str(row["team"])
            for row in self._query(
                "SELECT team_id, team FROM results WHERE season = ? AND round <= ? AND session = 'R' "
                "AND team IS NOT NULL ORDER BY round",
                [season, round_number],
                table="results",
            )
        }
        standings = []
        for row in rows:
            team = names.get(str(row["constructor_id"])) or str(row["constructor_name"])
            standings.append(
                TeamStanding(
                    position=integer(row["position"]),
                    team=team,
                    colour=driver("", None, team).colour,
                    points=number(row["points"]) or 0,
                    wins=integer(row["wins"]) or 0,
                    change=_change(before.get(str(row["constructor_id"])), integer(row["position"])),
                )
            )
        return standings

    def _weather(self, ref: SessionRef) -> Weather | None:
        rows = [row for row in self._rows(lambda: self._data.weather(ref)) if number(row["air_temp_c"]) is not None]
        if not rows:
            return None

        def span(column: str) -> tuple[float, float]:
            values = [float(row[column]) for row in rows if number(row[column]) is not None]
            return (min(values), max(values)) if values else (0.0, 0.0)

        humidity = [float(row["humidity_pct"]) for row in rows if number(row["humidity_pct"]) is not None]
        (air_min, air_max), (track_min, track_max) = span("air_temp_c"), span("track_temp_c")
        return Weather(
            air_temp_min_c=air_min,
            air_temp_max_c=air_max,
            track_temp_min_c=track_min,
            track_temp_max_c=track_max,
            humidity_pct=round(statistics.fmean(humidity), 1) if humidity else 0.0,
            rainfall=any(bool(row["rainfall"]) for row in rows),
        )

    def _rows(self, read: Any) -> list[dict[str, Any]]:
        """The rows a `RaceData` read returns, or none when the lake does not have them."""
        try:
            rows: list[dict[str, Any]] = read()
        except ToolError:
            return []
        return rows

    def _query(
        self, query: str, parameters: list[Any] | None = None, *, table: str = "sessions"
    ) -> list[dict[str, Any]]:
        try:
            frame = self._db.cursor().execute(query, parameters or []).df()
        except duckdb.CatalogException:  # the table has no file in the lake yet
            return []
        rows: list[dict[str, Any]] = frame.to_dict("records")  # type: ignore[assignment]
        return rows


def _summary(season: int, row: dict[str, Any], winner: Driver | None) -> RaceSummary:
    date = row["date"]
    return RaceSummary(
        season=season,
        round=int(row["round"]),
        grand_prix=grand_prix_fr(str(row["event"])),
        event=str(row["event"]),
        location=_text(row["location"]),
        country=_text(row["country"]),
        date=None if _text(date) is None else date.to_pydatetime().astimezone(UTC),
        sprint=bool(row["sprint"]),
        winner=winner,
    )


def _classification(results: list[dict[str, Any]], drivers: dict[str, Driver]) -> list[Classified]:
    winner_laps = integer(results[0]["laps"]) if results else None
    rows = []
    for row in results:
        position, grid, laps = integer(row["position"]), integer(row["grid_position"]), integer(row["laps"])
        text = _text(row["classified_position"]) or (str(position) if position else "")
        classified = text.isdigit()
        rows.append(
            Classified(
                position=position,
                position_text=text,
                driver=drivers[str(row["driver"])],
                number=_text(row["driver_number"]),
                grid=grid,
                # From a pit lane start (0), places are counted from the back of the grid.
                places_gained=(grid or len(results)) - position
                if classified and grid is not None and position
                else None,
                laps=laps,
                time_s=number(row["race_time_s"]),
                gap_s=number(row["gap_to_winner_s"]),
                laps_behind=winner_laps - laps if classified and winner_laps and laps and laps < winner_laps else None,
                status=_text(row["status"]),
                points=number(row["points"]) or 0,
            )
        )
    return rows


def _best_laps(laps: list[dict[str, Any]], drivers: dict[str, Driver]) -> list[BestLap]:
    best: dict[str, dict[str, Any]] = {}
    for lap in laps:
        if number(lap["lap_time_s"]) is None or lap["deleted"] is True:
            continue
        code = str(lap["driver"])
        if code not in best or lap["lap_time_s"] < best[code]["lap_time_s"]:
            best[code] = lap
    ordered = sorted(best.values(), key=lambda lap: lap["lap_time_s"])
    fastest = float(ordered[0]["lap_time_s"]) if ordered else 0.0
    return [
        BestLap(
            driver=drivers.get(str(lap["driver"])) or driver(str(lap["driver"]), None, _text(lap["team"])),
            lap=int(lap["lap_number"]),
            lap_time_s=round(float(lap["lap_time_s"]), 3),
            gap_s=round(float(lap["lap_time_s"]) - fastest, 3),
        )
        for lap in ordered
    ]


def _driver_laps(race: Race, laps: list[dict[str, Any]]) -> list[DriverLaps]:
    """Each driver's laps, the gap to the leader at the end of each: the time between their crossings of the line,
    the leader's being the first (`lap_end_session_s`, as `gaps_at_line` reads it)."""
    first: dict[int, float] = {}
    for lap in laps:
        if (end := number(lap["lap_end_session_s"])) is not None:
            number_ = int(lap["lap_number"])
            first[number_] = min(first.get(number_, end), end)
    of: dict[str, list[dict[str, Any]]] = {}
    for lap in sorted(laps, key=lambda row: int(row["lap_number"])):
        of.setdefault(str(lap["driver"]), []).append(lap)
    rows = []
    for classified in race.classification:
        mine = of.get(classified.driver.code, [])
        rows.append(
            DriverLaps(
                driver=classified.driver,
                grid=classified.grid,
                laps=[
                    Lap(
                        lap=int(lap["lap_number"]),
                        position=integer(lap["position"]),
                        gap_s=None
                        if (end := number(lap["lap_end_session_s"])) is None
                        else round(end - first[int(lap["lap_number"])], 3),
                        lap_time_s=number(lap["lap_time_s"]),
                        compound=_text(lap["compound"]),
                        tyre_age=integer(lap["tyre_life"]),
                        pit="in"
                        if number(lap["pit_in_session_s"]) is not None
                        else "out"
                        if number(lap["pit_out_session_s"]) is not None
                        else None,
                    )
                    for lap in mine
                ],
            )
        )
    return rows


def _stop(laps: dict[int, dict[str, Any]], stop: dict[str, Any]) -> Stop:
    if laps:
        loss = stop_loss(laps, stop)
        return Stop(
            stop_number=loss.stop_number,
            lap=loss.lap,
            pit_lane_time_s=loss.pit_lane_time_s,
            stationary_time_s=loss.stationary_time_s,
            time_lost_s=loss.time_lost_s,
            compound_after=loss.compound_after,
            neutralized=loss.neutralized,
        )
    return Stop(
        stop_number=int(stop["stop_number"]),
        lap=int(stop["lap"]),
        pit_lane_time_s=number(stop["pit_lane_time_s"]),
        stationary_time_s=number(stop["stationary_time_s"]),
        compound_after=_text(stop["compound_after"]),
    )


def _change(before: int | None, after: int | None) -> int | None:
    return before - after if before is not None and after is not None else None


def _text(value: Any) -> Any:
    """The value, or None for a null of the lake (None, NaN, pandas' NA)."""
    return None if value is None or bool(pd.isna(value)) else value
