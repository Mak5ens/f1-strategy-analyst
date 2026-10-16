"""Read access to the race data lake for the tools, with errors that say what is missing."""

from typing import Annotated, Any, Literal

import duckdb
import pandas as pd
from pydantic import AfterValidator, BaseModel, Field

from core.tools import ToolError

DriverCode = Annotated[
    str,
    Field(min_length=3, max_length=3, description="Three-letter driver code, e.g. LEC, VER, NOR"),
    AfterValidator(str.upper),
]


class SessionRef(BaseModel):
    season: int = Field(ge=2018, le=2100, description="Championship year, e.g. 2025")
    round: int = Field(ge=1, le=30, description="Round number in the season's calendar")
    session: Literal["R", "S"] = Field("R", description="R for the race, S for the sprint")

    def label(self) -> str:
        return f"{self.season} round {self.round} {'race' if self.session == 'R' else 'sprint'}"


# A lap that says something about pace: green flag only, not an in- or out-lap, not the standing start.
GREEN = "1"


def is_clean(lap: dict[str, Any]) -> bool:
    return bool(
        lap["lap_number"] > 1
        and _missing(lap["pit_in_session_s"])
        and _missing(lap["pit_out_session_s"])
        and lap["track_status"] == GREEN
        and not lap["deleted"]
        and not _missing(lap["lap_time_s"])
    )


def is_neutralized(track_status: object) -> bool:
    """Safety car (4), red flag (5) or virtual safety car (6, 7) at some point of the lap."""
    return not _missing(track_status) and any(code in str(track_status) for code in "4567")


def _missing(value: object) -> bool:
    return value is None or bool(pd.isna(value))  # type: ignore[call-overload]


def number(value: object) -> float | None:
    """A float from a lake value, None for null or NaN."""
    return None if _missing(value) else float(value)  # type: ignore[arg-type]


def integer(value: object) -> int | None:
    return None if _missing(value) else int(value)  # type: ignore[call-overload]


class RaceData:
    """Each query runs on its own cursor: a DuckDB connection is not safe across threads, and the evaluation
    harness runs cases in parallel."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._db = connection

    def laps(self, ref: SessionRef) -> list[dict[str, Any]]:
        laps = self._rows("laps", ref, order="driver, lap_number")
        if not laps:
            raise ToolError(f"No lap data for the {ref.label()}: not ingested, or no such session.")
        return laps

    def driver_laps(self, ref: SessionRef, driver: str) -> dict[int, dict[str, Any]]:
        """The driver's laps by lap number."""
        laps = self.laps(ref)
        mine = {int(lap["lap_number"]): lap for lap in laps if lap["driver"] == driver}
        if not mine:
            drivers = ", ".join(sorted({str(lap["driver"]) for lap in laps}))
            raise ToolError(f"No driver {driver} in the {ref.label()}. Drivers: {drivers}.")
        return mine

    def pit_stops(self, ref: SessionRef, driver: str) -> list[dict[str, Any]]:
        return [stop for stop in self._rows("pit_stops", ref, order="stop_number") if stop["driver"] == driver]

    def stints(self, ref: SessionRef) -> list[dict[str, Any]]:
        return self._rows("stints", ref, order="driver, stint")

    def race_control_messages(self, ref: SessionRef) -> list[dict[str, Any]]:
        return self._rows("race_control_messages", ref, order="time_utc")

    def weather(self, ref: SessionRef) -> list[dict[str, Any]]:
        """One row a minute; empty when the session has none."""
        return self._rows("weather", ref, order="session_time_s")

    def events(self, season: int) -> list[dict[str, Any]]:
        """The race weekends of a season in the data, with their name, place and country."""
        return self._query(
            "SELECT DISTINCT round, event_name, location, country FROM sessions WHERE season = ? ORDER BY round",
            [season],
            table="sessions",
        )

    def session_codes(self, season: int, round_number: int) -> list[str]:
        rows = self._query(
            "SELECT session FROM sessions WHERE season = ? AND round = ? ORDER BY start_utc",
            [season, round_number],
            table="sessions",
        )
        return [str(row["session"]) for row in rows]

    def drivers(self, season: int, round_number: int) -> list[dict[str, Any]]:
        """Code, name and team of the drivers of the race, in finishing order."""
        rows = self._query(
            "SELECT driver AS code, coalesce(full_name, driver) AS name, team FROM results "
            "WHERE season = ? AND round = ? AND session = 'R' ORDER BY position NULLS LAST",
            [season, round_number],
            table="results",
        )
        return [{**row, "team": None if _missing(row["team"]) else row["team"]} for row in rows]

    def results(self, season: int, round_number: int, session: str) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM results WHERE season = ? AND round = ? AND session = ? ORDER BY position NULLS LAST",
            [season, round_number, session],
            table="results",
        )

    def fastest_lap(self, season: int, round_number: int, session: str) -> dict[str, Any] | None:
        rows = self._query(
            "SELECT driver, lap_number, lap_time_s FROM laps WHERE season = ? AND round = ? AND session = ? "
            "AND lap_time_s IS NOT NULL AND NOT coalesce(deleted, false) ORDER BY lap_time_s LIMIT 1",
            [season, round_number, session],
            table="laps",
        )
        return rows[0] if rows else None

    def _query(self, query: str, parameters: list[Any], *, table: str) -> list[dict[str, Any]]:
        try:
            frame = self._db.cursor().execute(query, parameters).df()
        except duckdb.CatalogException as error:
            raise ToolError(f"No {table} data in the lake: run `just ingest`.") from error
        rows: list[dict[str, Any]] = frame.to_dict("records")  # type: ignore[assignment]
        return rows

    def _rows(self, table: str, ref: SessionRef, *, order: str) -> list[dict[str, Any]]:
        query = f"SELECT * FROM {table} WHERE season = ? AND round = ? AND session = ? ORDER BY {order}"
        try:
            frame = self._db.cursor().execute(query, [ref.season, ref.round, ref.session]).df()
        except duckdb.CatalogException as error:
            raise ToolError(f"No {table} data in the lake: run `just ingest {ref.season}`.") from error
        rows: list[dict[str, Any]] = frame.to_dict("records")  # type: ignore[assignment]
        return rows
