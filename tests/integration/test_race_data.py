"""The race data pipeline against the real sources: values checked by hand against the official results
of the 2025 Italian Grand Prix, and cross-checked with Jolpica-F1, a source the pipeline does not use for laps
or pit stops. Needs the network; the FastF1 cache makes reruns fast. Plus the S3 store of the stack.
"""

from collections import Counter

import duckdb
import pyarrow as pa
import pytest

from core.lake import Lake, LakeSettings
from f1.data import connect
from f1.data.ingest import Ingester, IngestSettings
from f1.data.sources import FastF1Source, JolpicaClient, OpenF1Client

pytestmark = pytest.mark.integration

SEASON, ROUND = 2025, 16  # Monza


@pytest.fixture(scope="module")
def monza(tmp_path_factory: pytest.TempPathFactory) -> duckdb.DuckDBPyConnection:
    lake = Lake(LakeSettings(uri=str(tmp_path_factory.mktemp("lake")), _env_file=None))
    settings = IngestSettings()
    with OpenF1Client() as openf1, JolpicaClient() as jolpica:
        ingester = Ingester(lake, FastF1Source(settings.fastf1_cache), openf1, jolpica, settings)
        outcomes = list(ingester.ingest_season(SEASON, rounds=[ROUND]))
    assert [outcome.status for outcome in outcomes] == ["ingested"], outcomes
    return connect(lake)


def test_official_results(monza: duckdb.DuckDBPyConnection) -> None:
    podium = monza.sql(
        "SELECT driver, grid_position, laps, race_time_s, gap_to_winner_s FROM results ORDER BY position LIMIT 4"
    ).fetchall()
    assert podium == [
        ("VER", 1, 53, pytest.approx(4404.325), None),  # 1:13:24.325
        ("NOR", 2, 53, None, pytest.approx(19.207)),
        ("PIA", 3, 53, None, pytest.approx(21.351)),
        ("LEC", 4, 53, None, pytest.approx(25.624)),
    ]


def test_fastest_lap(monza: duckdb.DuckDBPyConnection) -> None:
    fastest = monza.sql("SELECT driver, lap_time_s FROM laps ORDER BY lap_time_s LIMIT 1").fetchone()
    assert fastest == ("NOR", pytest.approx(80.901))  # 1:20.901


def test_strategies(monza: duckdb.DuckDBPyConnection) -> None:
    stints = monza.sql(
        "SELECT driver, list(compound ORDER BY stint), list(end_lap ORDER BY stint) FROM stints "
        "WHERE driver IN ('VER', 'LEC') GROUP BY driver ORDER BY driver"
    ).fetchall()
    assert stints == [("LEC", ["MEDIUM", "HARD"], [33, 53]), ("VER", ["MEDIUM", "HARD"], [37, 53])]
    norris = monza.sql("SELECT lap, pit_lane_time_s, stationary_time_s FROM pit_stops WHERE driver = 'NOR'").fetchall()
    assert norris == [(46, pytest.approx(27.454), pytest.approx(5.9))]  # the slow stop that swapped the McLarens


def test_pit_stops_match_jolpica(monza: duckdb.DuckDBPyConnection) -> None:
    with JolpicaClient() as jolpica:
        data = jolpica.get(f"/{SEASON}/{ROUND}/pitstops/", {"limit": 100})
    stops = data["MRData"]["RaceTable"]["Races"][0]["PitStops"]
    driver_codes = dict(monza.sql("SELECT driver_id, driver FROM results").fetchall())
    expected = Counter((driver_codes[stop["driverId"]], int(stop["lap"])) for stop in stops)
    ours = Counter(monza.sql("SELECT driver, lap FROM pit_stops WHERE NOT red_flag").fetchall())
    assert ours == expected


def test_lap_times_match_jolpica(monza: duckdb.DuckDBPyConnection) -> None:
    with JolpicaClient() as jolpica:
        data = jolpica.get(f"/{SEASON}/{ROUND}/drivers/leclerc/laps/", {"limit": 100})
    expected = {}
    for jolpica_lap in data["MRData"]["RaceTable"]["Races"][0]["Laps"]:
        minutes, seconds = jolpica_lap["Timings"][0]["time"].split(":")
        expected[int(jolpica_lap["number"])] = int(minutes) * 60 + float(seconds)
    ours = dict(monza.sql("SELECT lap_number, lap_time_s FROM laps WHERE driver = 'LEC'").fetchall())
    assert len(ours) == len(expected) == 53
    for number, lap_time in expected.items():
        assert ours[number] == pytest.approx(lap_time, abs=0.001), number


def test_the_s3_store_of_the_stack() -> None:
    lake = Lake()
    assert lake.url("x").startswith("s3://"), "set LAKE_URI to the S3 store in .env (see .env.example)"
    lake.write_parquet("_smoke/table.parquet", pa.table({"lap": [1, 2]}))
    assert lake.connect(["_smoke"]).sql("SELECT count(*) FROM _smoke").fetchone() == (2,)
