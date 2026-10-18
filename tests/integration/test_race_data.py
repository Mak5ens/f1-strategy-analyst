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
from f1.grand_prix import GrandPrix

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
        "SELECT driver, grid_position, laps, race_time_s, gap_to_winner_s FROM results WHERE session = 'R' "
        "ORDER BY position LIMIT 4"
    ).fetchall()
    assert podium == [
        ("VER", 1, 53, pytest.approx(4404.325), None),  # 1:13:24.325
        ("NOR", 2, 53, None, pytest.approx(19.207)),
        ("PIA", 3, 53, None, pytest.approx(21.351)),
        ("LEC", 4, 53, None, pytest.approx(25.624)),
    ]


def test_fastest_lap(monza: duckdb.DuckDBPyConnection) -> None:
    fastest = monza.sql(
        "SELECT driver, lap_time_s FROM laps WHERE session = 'R' ORDER BY lap_time_s LIMIT 1"
    ).fetchone()
    assert fastest == ("NOR", pytest.approx(80.901))  # 1:20.901


def test_strategies(monza: duckdb.DuckDBPyConnection) -> None:
    stints = monza.sql(
        "SELECT driver, list(compound ORDER BY stint), list(end_lap ORDER BY stint) FROM stints "
        "WHERE session = 'R' AND driver IN ('VER', 'LEC') GROUP BY driver ORDER BY driver"
    ).fetchall()
    assert stints == [("LEC", ["MEDIUM", "HARD"], [33, 53]), ("VER", ["MEDIUM", "HARD"], [37, 53])]
    norris = monza.sql("SELECT lap, pit_lane_time_s, stationary_time_s FROM pit_stops WHERE driver = 'NOR'").fetchall()
    assert norris == [(46, pytest.approx(27.454), pytest.approx(5.9))]  # the slow stop that swapped the McLarens


def test_every_session_of_the_weekend(monza: duckdb.DuckDBPyConnection) -> None:
    sessions = monza.sql("SELECT session FROM sessions ORDER BY start_utc").fetchall()
    assert [code for (code,) in sessions] == ["FP1", "FP2", "FP3", "Q", "R"]
    pole = monza.sql("SELECT driver, q3_s FROM results WHERE session = 'Q' ORDER BY position LIMIT 1").fetchone()
    assert pole == ("VER", pytest.approx(78.792))  # 1:18.792, the fastest lap in F1 history
    assert monza.sql("SELECT DISTINCT session FROM pit_stops").fetchall() == [("R",)]


def test_pit_stops_match_jolpica(monza: duckdb.DuckDBPyConnection) -> None:
    with JolpicaClient() as jolpica:
        data = jolpica.get(f"/{SEASON}/{ROUND}/pitstops/", {"limit": 100})
    stops = data["MRData"]["RaceTable"]["Races"][0]["PitStops"]
    driver_codes = dict(monza.sql("SELECT driver_id, driver FROM results WHERE session = 'R'").fetchall())
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
    ours = dict(monza.sql("SELECT lap_number, lap_time_s FROM laps WHERE session = 'R' AND driver = 'LEC'").fetchall())
    assert len(ours) == len(expected) == 53
    for number, lap_time in expected.items():
        assert ours[number] == pytest.approx(lap_time, abs=0.001), number


def test_the_s3_store_of_the_stack() -> None:
    lake = Lake()
    assert lake.url("x").startswith("s3://"), "set LAKE_URI to the S3 store in .env (see .env.example)"
    lake.write_parquet("_smoke/table.parquet", pa.table({"lap": [1, 2]}))
    assert lake.connect(["_smoke"]).sql("SELECT count(*) FROM _smoke").fetchone() == (2,)


def test_the_race_page(monza: duckdb.DuckDBPyConnection) -> None:
    # What the site shows of Monza 2025 (LAB-202), against the official classification and standings after round 16.
    race = GrandPrix(monza).race(SEASON, ROUND)
    assert race is not None and race.summary.grand_prix == "Grand Prix d'Italie"

    top = [(row.driver.code, row.grid, row.places_gained, row.points) for row in race.classification[:6]]
    assert top == [("VER", 1, 0, 25), ("NOR", 2, 0, 18), ("PIA", 3, 0, 15), ("LEC", 4, 0, 12), ("RUS", 5, 0, 10),
                   ("HAM", 10, 4, 8)]  # fmt: skip
    assert [row.position_text for row in race.classification[-2:]] == ["R", "W"]  # Alonso retired, Hülkenberg DNS
    assert race.fastest_lap and (race.fastest_lap.driver.code, race.fastest_lap.lap_time_s) == ("NOR", 80.901)
    strategies = {strategy.driver.code: strategy for strategy in race.strategies}
    assert [(stint.compound, stint.end_lap) for stint in strategies["LEC"].stints] == [("MEDIUM", 33), ("HARD", 53)]
    (stop,) = strategies["NOR"].stops
    assert stop.lap == 46 and stop.pit_lane_time_s == pytest.approx(27.454)
    assert race.neutralizations == []
    standings = [(row.driver.code, row.points) for row in race.driver_standings[:3]]
    assert standings == [("PIA", 324), ("NOR", 293), ("VER", 230)]
    teams = [(row.team, row.points) for row in race.team_standings[:2]]
    assert teams == [("McLaren", 617), ("Ferrari", 280)]
