"""Ingest race data into the lake, one round at a time: `just ingest 2025`, or `f1-ingest 2024 2025 --round 3`.

A round is the unit of work: its sessions (sprint and race) and the standings after it. Its tables are written
first, then a manifest under `_manifest/`. A round with a manifest of the current schema version is skipped, so
a rerun only fetches what is missing, and an interrupted round is rewritten whole: files are overwritten by key,
never appended, so nothing is duplicated.
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

import pandas as pd
import pyarrow as pa
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.lake import Lake
from f1.data import schema, transform
from f1.data.sources import (
    EventInfo,
    FastF1Source,
    JolpicaClient,
    OpenF1Client,
    RateLimitExceededError,
    SessionData,
)

log = logging.getLogger("f1.ingest")


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INGEST_", env_file=".env", extra="ignore")

    # HTTP cache of FastF1: a rerun, even with --force, reads it instead of the network.
    fastf1_cache: Path = Path(".cache/fastf1")
    # The live timing archive publishes a session's data within a few hours after it ends.
    availability_delay_hours: float = 6.0
    # FastF1 refuses more than 500 calls per hour; a full season needs more. Wait, then resume.
    rate_limit_pause_minutes: float = 15.0
    max_rate_limit_pauses: int = 8


class RaceSource(Protocol):
    def schedule(self, season: int) -> list[EventInfo]: ...
    def session(self, season: int, round_number: int, code: str) -> SessionData: ...


class PitSource(Protocol):
    def pit_stops(self, session_key: int) -> list[dict[str, Any]]: ...


class StandingsSource(Protocol):
    def driver_standings(self, season: int, round_number: int) -> list[dict[str, Any]]: ...
    def constructor_standings(self, season: int, round_number: int) -> list[dict[str, Any]]: ...


class IngestError(Exception):
    pass


Status = Literal["ingested", "up_to_date", "not_ready", "failed"]


@dataclass(frozen=True)
class RoundOutcome:
    season: int
    round: int
    event_name: str
    status: Status
    detail: str = ""


def manifest_key(season: int, round_number: int) -> str:
    return f"_manifest/{season}/{round_number:02d}.json"


def table_key(table: str, season: int, round_number: int, code: str | None = None) -> str:
    suffix = f"-{code}" if code else ""
    return f"{table}/{season}/{round_number:02d}{suffix}.parquet"


class Ingester:
    def __init__(
        self,
        lake: Lake,
        race: RaceSource,
        pits: PitSource,
        standings: StandingsSource,
        settings: IngestSettings | None = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._lake = lake
        self._race = race
        self._pits = pits
        self._standings = standings
        self._settings = settings or IngestSettings()
        self._now = now
        self._sleep = sleep

    def ingest_season(
        self, season: int, rounds: Sequence[int] | None = None, *, force: bool = False
    ) -> Iterator[RoundOutcome]:
        """Ingest the rounds one by one, yielding each outcome as soon as it is known."""
        for event in self._race.schedule(season):
            if not rounds or event.round in rounds:
                yield self.ingest_round(event, force=force)

    def ingest_round(self, event: EventInfo, *, force: bool = False) -> RoundOutcome:
        def outcome(status: Status, detail: str = "") -> RoundOutcome:
            return RoundOutcome(event.season, event.round, event.event_name, status, detail)

        manifest = self._lake.read_json(manifest_key(event.season, event.round))
        if not force and manifest and manifest.get("schema_version") == schema.SCHEMA_VERSION:
            return outcome("up_to_date")
        if not event.sessions:
            return outcome("not_ready", "no sprint or race in the schedule")
        ready_at = max(event.sessions.values()) + timedelta(hours=self._settings.availability_delay_hours)
        if self._now() < ready_at:
            return outcome("not_ready", f"data expected after {ready_at:%Y-%m-%d %H:%M} UTC")

        for pause in range(self._settings.max_rate_limit_pauses + 1):
            try:
                rows = self._write_round(event)
                break
            except RateLimitExceededError as error:
                if pause == self._settings.max_rate_limit_pauses:
                    return outcome("failed", f"rate limit still reached after {pause} pauses: {error}")
                minutes = self._settings.rate_limit_pause_minutes
                log.warning("%s: rate limit reached (%s), pausing %.0f min", event.event_name, error, minutes)
                self._sleep(minutes * 60)
            except Exception as error:
                log.exception("%s %s round %s failed", event.event_name, event.season, event.round)
                return outcome("failed", f"{type(error).__name__}: {error}")

        self._lake.write_json(
            manifest_key(event.season, event.round),
            {
                "schema_version": schema.SCHEMA_VERSION,
                "season": event.season,
                "round": event.round,
                "event_name": event.event_name,
                "ingested_at": self._now().isoformat(),
                "rows": rows,
            },
        )
        total = sum(count for tables in rows.values() for count in tables.values())
        return outcome("ingested", f"{total} rows")

    def _write_round(self, event: EventInfo) -> dict[str, dict[str, int]]:
        """Fetch everything, then write. A failed fetch writes nothing; a failed write leaves no manifest,
        so the next run rewrites the round."""
        tables: dict[str, pa.Table] = {}
        for code in sorted(event.sessions, key=lambda code: event.sessions[code]):
            for name, table in self._session_tables(event, code).items():
                tables[table_key(name, event.season, event.round, code)] = table
        key = {"season": event.season, "round": event.round}
        drivers = transform.driver_standings_rows(self._standings.driver_standings(event.season, event.round))
        teams = transform.constructor_standings_rows(self._standings.constructor_standings(event.season, event.round))
        tables[table_key("driver_standings", event.season, event.round)] = transform.to_table(
            drivers, schema.DRIVER_STANDINGS, **key
        )
        tables[table_key("constructor_standings", event.season, event.round)] = transform.to_table(
            teams, schema.CONSTRUCTOR_STANDINGS, **key
        )

        rows: dict[str, dict[str, int]] = {}
        for path, table in tables.items():
            self._lake.write_parquet(path, table)
            name, _, file_name = path.split("/")
            rows.setdefault(file_name.removesuffix(".parquet"), {})[name] = table.num_rows
        return rows

    def _session_tables(self, event: EventInfo, code: str) -> dict[str, pa.Table]:
        data = self._race.session(event.season, event.round, code)
        laps = transform.laps(data.laps)
        if laps.empty:
            raise IngestError(f"no lap data for session {code}: not published yet, or the session did not run")
        session_key = data.info.get("session_key")
        openf1_pits = self._pits.pit_stops(int(session_key)) if session_key else []

        key: dict[str, int | str] = {"season": event.season, "round": event.round, "session": code}
        frames: dict[str, tuple[pd.DataFrame, pa.Schema]] = {
            "sessions": (pd.DataFrame([data.info]), schema.SESSIONS),
            "laps": (laps, schema.LAPS),
            "stints": (transform.stints(laps), schema.STINTS),
            "pit_stops": (transform.pit_stops(laps, openf1_pits), schema.PIT_STOPS),
            "race_control_messages": (
                transform.race_control_messages(data.race_control_messages),
                schema.RACE_CONTROL_MESSAGES,
            ),
            "weather": (transform.weather(data.weather), schema.WEATHER),
            "results": (transform.results(data.results), schema.RESULTS),
        }
        return {name: transform.to_table(frame, table_schema, **key) for name, (frame, table_schema) in frames.items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="f1-ingest",
        description="Ingest race data into the lake. Rounds already stored are skipped: "
        "a rerun only fetches what is missing.",
    )
    parser.add_argument("seasons", nargs="+", type=int, help="e.g. 2025, or 2024 2025 2026")
    parser.add_argument("--round", dest="rounds", type=int, action="append", help="only this round (repeatable)")
    parser.add_argument("--force", action="store_true", help="rewrite rounds already stored")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for noisy in ("fastf1", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("fastf1").handlers.clear()  # FastF1 adds its own handler: every line would print twice

    settings = IngestSettings()
    lake = Lake()
    openf1, jolpica = OpenF1Client(), JolpicaClient()
    ingester = Ingester(lake, FastF1Source(settings.fastf1_cache), openf1, jolpica, settings)
    outcomes: list[RoundOutcome] = []
    try:
        for season in args.seasons:
            for outcome in ingester.ingest_season(season, args.rounds, force=args.force):
                log.info(
                    "%s round %02d %-28s %-10s %s",
                    outcome.season,
                    outcome.round,
                    outcome.event_name,
                    outcome.status,
                    outcome.detail,
                )
                outcomes.append(outcome)
    finally:
        openf1.close()
        jolpica.close()

    statuses = ("ingested", "up_to_date", "not_ready", "failed")
    counts = {status: sum(outcome.status == status for outcome in outcomes) for status in statuses}
    log.info("done: %s", ", ".join(f"{count} {status}" for status, count in counts.items()))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
