"""The orchestration of `just ingest`, with fake sources and a lake in a temporary folder: idempotence,
resumption after a failure, rate limit pauses, rounds not run yet."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from core.lake import Lake, LakeSettings
from f1.data import connect, schema
from f1.data.ingest import Ingester, IngestSettings, RoundOutcome, manifest_key
from f1.data.sources import EventInfo, RateLimitExceededError, SessionData

NOW = datetime(2025, 9, 10, tzinfo=UTC)
MONZA = EventInfo(2025, 16, "Italian Grand Prix", {"R": datetime(2025, 9, 7, 13, tzinfo=UTC)})
BAKU = EventInfo(2025, 17, "Azerbaijan Grand Prix", {"R": datetime(2025, 9, 21, 11, tzinfo=UTC)})  # after NOW
AUSTIN = EventInfo(
    2025,
    19,
    "United States Grand Prix",
    {"S": datetime(2025, 10, 18, 17, tzinfo=UTC), "R": datetime(2025, 10, 19, 19, tzinfo=UTC)},
)


def session_data(session_key: int) -> SessionData:
    laps = pd.DataFrame(
        {
            "Driver": ["LEC", "LEC", "VER", "VER"],
            "DriverNumber": ["16", "16", "1", "1"],
            "Team": ["Ferrari", "Ferrari", "Red Bull Racing", "Red Bull Racing"],
            "LapNumber": [1.0, 2.0, 1.0, 2.0],
            "LapTime": pd.to_timedelta([81.0, 80.5, 80.9, 80.2], unit="s"),
            "Stint": [1.0, 1.0, 1.0, 1.0],
            "Compound": ["MEDIUM"] * 4,
        }
    )
    results = pd.DataFrame(
        {
            "Abbreviation": ["VER", "LEC"],
            "DriverNumber": ["1", "16"],
            "Position": [1.0, 2.0],
            "Status": ["Finished"] * 2,
        }
    )
    return SessionData(
        info={"session_name": "Race", "session_key": session_key, "start_utc": datetime(2025, 9, 7, 13)},
        laps=laps,
        results=results,
        race_control_messages=pd.DataFrame(),
        weather=pd.DataFrame(),
    )


class FakeSources:
    def __init__(self, events: list[EventInfo]) -> None:
        self.events = events
        self.session_calls: list[tuple[int, int, str]] = []
        self.failures: list[BaseException] = []  # raised by the next session() calls, in order
        self.without_laps = False

    def schedule(self, season: int) -> list[EventInfo]:
        return [event for event in self.events if event.season == season]

    def session(self, season: int, round_number: int, code: str) -> SessionData:
        self.session_calls.append((season, round_number, code))
        if self.failures:
            raise self.failures.pop(0)
        data = session_data(9000 + round_number)
        return replace(data, laps=pd.DataFrame()) if self.without_laps else data

    def pit_stops(self, session_key: int) -> list[dict[str, Any]]:
        return [{"driver_number": 16, "lap_number": 1, "lane_duration": 24.0, "stop_duration": 2.4}]

    def driver_standings(self, season: int, round_number: int) -> list[dict[str, Any]]:
        return [{"position": "1", "points": "25", "wins": "1", "Driver": {"driverId": "max_verstappen"}}]

    def constructor_standings(self, season: int, round_number: int) -> list[dict[str, Any]]:
        return [{"position": "1", "points": "25", "wins": "1", "Constructor": {"constructorId": "red_bull"}}]


@pytest.fixture
def lake(tmp_path: Path) -> Lake:
    return Lake(LakeSettings(uri=str(tmp_path / "lake"), _env_file=None))


def ingester(lake: Lake, sources: FakeSources, sleeps: list[float] | None = None) -> Ingester:
    settings = IngestSettings(_env_file=None, rate_limit_pause_minutes=1, max_rate_limit_pauses=2)
    return Ingester(
        lake,
        sources,
        sources,
        sources,
        settings,
        now=lambda: NOW,
        sleep=(sleeps if sleeps is not None else []).append,
    )


def statuses(outcomes: list[RoundOutcome]) -> dict[int, str]:
    return {outcome.round: outcome.status for outcome in outcomes}


def test_ingests_past_rounds_and_waits_for_the_others(lake: Lake) -> None:
    sources = FakeSources([MONZA, BAKU])
    outcomes = list(ingester(lake, sources).ingest_season(2025))
    assert statuses(outcomes) == {16: "ingested", 17: "not_ready"}
    assert sources.session_calls == [(2025, 16, "R")]
    connection = connect(lake)
    for table in schema.TABLES:
        assert connection.sql(f"SELECT count(*) FROM {table}").fetchone() is not None, table
    assert connection.sql("SELECT driver, stationary_time_s FROM pit_stops").fetchall() == [("LEC", 2.4)]
    assert lake.read_json(manifest_key(2025, 16)) is not None


def test_a_rerun_fetches_nothing_and_duplicates_nothing(lake: Lake) -> None:
    sources = FakeSources([MONZA])
    list(ingester(lake, sources).ingest_season(2025))
    outcomes = list(ingester(lake, sources).ingest_season(2025))
    assert statuses(outcomes) == {16: "up_to_date"}
    assert len(sources.session_calls) == 1
    assert connect(lake).sql("SELECT count(*) FROM laps").fetchone() == (4,)


def test_force_rewrites_without_duplicating(lake: Lake) -> None:
    sources = FakeSources([MONZA])
    list(ingester(lake, sources).ingest_season(2025))
    outcomes = list(ingester(lake, sources).ingest_season(2025, force=True))
    assert statuses(outcomes) == {16: "ingested"}
    assert connect(lake).sql("SELECT count(*) FROM laps").fetchone() == (4,)


def test_a_new_schema_version_rewrites_the_round(lake: Lake) -> None:
    sources = FakeSources([MONZA])
    list(ingester(lake, sources).ingest_season(2025))
    lake.write_json(manifest_key(2025, 16), {"schema_version": schema.SCHEMA_VERSION - 1})
    assert statuses(list(ingester(lake, sources).ingest_season(2025))) == {16: "ingested"}


def test_a_failed_round_is_retried_on_the_next_run(lake: Lake) -> None:
    sources = FakeSources([MONZA])
    sources.failures = [ConnectionError("live timing unreachable")]
    first = list(ingester(lake, sources).ingest_season(2025))
    assert statuses(first) == {16: "failed"}
    assert "live timing unreachable" in first[0].detail
    assert lake.read_json(manifest_key(2025, 16)) is None
    assert statuses(list(ingester(lake, sources).ingest_season(2025))) == {16: "ingested"}


def test_a_session_without_laps_fails_the_round(lake: Lake) -> None:
    sources = FakeSources([MONZA])
    sources.without_laps = True
    assert statuses(list(ingester(lake, sources).ingest_season(2025))) == {16: "failed"}
    assert lake.keys("laps") == []


def test_rate_limit_pauses_then_resumes(lake: Lake) -> None:
    sources = FakeSources([MONZA])
    sources.failures = [RateLimitExceededError("any API: 500 calls/h")] * 2
    sleeps: list[float] = []
    outcomes = list(ingester(lake, sources, sleeps).ingest_season(2025))
    assert statuses(outcomes) == {16: "ingested"}
    assert sleeps == [60.0, 60.0]


def test_rate_limit_gives_up_after_the_last_pause(lake: Lake) -> None:
    sources = FakeSources([MONZA])
    sources.failures = [RateLimitExceededError("any API: 500 calls/h")] * 3
    assert statuses(list(ingester(lake, sources).ingest_season(2025))) == {16: "failed"}


def test_sprint_weekends_store_both_sessions(lake: Lake) -> None:
    sources = FakeSources([AUSTIN])
    settings_now = datetime(2025, 10, 25, tzinfo=UTC)
    run = Ingester(lake, sources, sources, sources, IngestSettings(_env_file=None), now=lambda: settings_now)
    assert statuses(list(run.ingest_season(2025))) == {19: "ingested"}
    assert sources.session_calls == [(2025, 19, "S"), (2025, 19, "R")]
    assert lake.keys("laps") == ["laps/2025/19-R.parquet", "laps/2025/19-S.parquet"]


def test_only_the_requested_rounds(lake: Lake) -> None:
    sources = FakeSources([MONZA, BAKU])
    assert statuses(list(ingester(lake, sources).ingest_season(2025, rounds=[17]))) == {17: "not_ready"}
    assert sources.session_calls == []
