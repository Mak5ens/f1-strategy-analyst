"""Transforms on small frames shaped like FastF1's, with the cases that broke naive versions:
a pit lane start, a retirement in the pits, a red flag, a stop that only OpenF1 saw."""

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from f1.data import schema, transform


def seconds(value: float | None) -> np.timedelta64:
    """A FastF1-style duration; NaT for None."""
    return np.timedelta64("NaT", "ns") if value is None else np.timedelta64(round(value * 1e9), "ns")


def lap(
    driver: str,
    number: str,
    lap_number: int,
    *,
    stint: int = 1,
    compound: str = "MEDIUM",
    tyre_life: int | None = None,
    pit_in: float | None = None,
    pit_out: float | None = None,
    status: str = "1",
) -> dict[str, Any]:
    return {
        "Driver": driver,
        "DriverNumber": number,
        "Team": "Ferrari" if driver == "LEC" else "McLaren",
        "LapNumber": float(lap_number),
        "LapTime": seconds(80 + lap_number / 10),
        "Sector1Time": seconds(26),
        "Sector2Time": seconds(None),
        "Sector3Time": seconds(27),
        "LapStartTime": seconds(3000 + 80 * lap_number),
        "Position": 1.0,
        "Stint": float(stint),
        "Compound": compound,
        "TyreLife": float(tyre_life if tyre_life is not None else lap_number),
        "FreshTyre": True,
        "PitInTime": seconds(pit_in),
        "PitOutTime": seconds(pit_out),
        "TrackStatus": status,
        "IsAccurate": True,
        "IsPersonalBest": False,
        "Deleted": False,
        "DeletedReason": "",
        "FastF1Generated": False,
    }


@pytest.fixture
def raw_laps() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # LEC: starts from the pit lane (out time on lap 1, no in-lap before), one stop on lap 2.
            lap("LEC", "16", 1, pit_out=2990.0),
            lap("LEC", "16", 2, pit_in=3155.0),
            lap("LEC", "16", 3, stint=2, compound="HARD", tyre_life=1, pit_out=3180.25),
            lap("LEC", "16", 4, stint=2, compound="HARD", tyre_life=2, status="45"),
            # NOR: a tyre change under red flag on lap 3, then retires into the pits on lap 4.
            lap("NOR", "4", 1),
            lap("NOR", "4", 2),
            lap("NOR", "4", 3, pit_in=3240.0, status="15"),
            lap("NOR", "4", 4, stint=2, compound="SOFT", tyre_life=1, pit_out=3900.0, pit_in=3990.0),
        ]
    )


def test_laps_renames_and_converts_durations(raw_laps: pd.DataFrame) -> None:
    laps = transform.laps(raw_laps)
    first = laps.iloc[0]
    assert first["driver"] == "LEC"
    assert first["lap_time_s"] == pytest.approx(80.1)
    assert np.isnan(first["sector2_s"])
    assert list(laps["driver"]) == ["LEC"] * 4 + ["NOR"] * 4


def test_stints(raw_laps: pd.DataFrame) -> None:
    stints = transform.stints(transform.laps(raw_laps))
    lec = stints[stints["driver"] == "LEC"].to_dict("records")
    assert [(s["stint"], s["compound"], s["start_lap"], s["end_lap"], s["laps"]) for s in lec] == [
        (1, "MEDIUM", 1, 2, 2),
        (2, "HARD", 3, 4, 2),
    ]
    assert lec[1]["tyre_life_start"] == 1


def test_pit_stops_need_an_in_lap_followed_by_an_out_lap(raw_laps: pd.DataFrame) -> None:
    stops = transform.pit_stops(transform.laps(raw_laps))
    rows = stops[["driver", "stop_number", "lap", "pit_lane_time_s", "compound_before", "compound_after"]]
    assert rows.to_dict("records") == [
        {
            "driver": "LEC",
            "stop_number": 1,
            "lap": 2,
            "pit_lane_time_s": 25.25,
            "compound_before": "MEDIUM",
            "compound_after": "HARD",
        },
        {
            "driver": "NOR",
            "stop_number": 1,
            "lap": 3,
            "pit_lane_time_s": 660.0,
            "compound_before": "MEDIUM",
            "compound_after": "SOFT",
        },
    ]  # no stop for LEC's pit lane start, none for NOR's retirement
    assert list(stops["red_flag"]) == [False, True]
    assert set(stops["source"]) == {"fastf1"}


def test_openf1_adds_stationary_time_and_missing_stops(raw_laps: pd.DataFrame) -> None:
    openf1 = [
        {"driver_number": 16, "lap_number": 2, "lane_duration": 25.3, "stop_duration": 2.4},
        {"driver_number": 4, "lap_number": 2, "lane_duration": 24.0, "stop_duration": 2.1},  # FastF1 missed it
        {"driver_number": 99, "lap_number": 5, "lane_duration": 24.0},  # not in the session: dropped
    ]
    stops = transform.pit_stops(transform.laps(raw_laps), openf1).set_index(["driver", "lap"])
    assert stops.loc[("LEC", 2), "pit_lane_time_s"] == 25.25  # FastF1's timing wins
    assert stops.loc[("LEC", 2), "stationary_time_s"] == 2.4
    assert stops.loc[("LEC", 2), "source"] == "fastf1+openf1"
    assert stops.loc[("NOR", 2), "pit_lane_time_s"] == 24.0
    assert stops.loc[("NOR", 2), "source"] == "openf1"
    assert stops.loc[("NOR", 2), "compound_after"] == "MEDIUM"
    assert stops.xs("NOR")["stop_number"].tolist() == [1, 2]
    assert len(stops) == 3


def test_results_split_race_time_and_gap() -> None:
    raw = pd.DataFrame(
        {
            "Abbreviation": ["NOR", "VER", "COL", "ALO"],
            "DriverNumber": ["4", "1", "43", "14"],
            "Position": [2.0, 1.0, 17.0, 19.0],
            "ClassifiedPosition": ["2", "1", "17", "R"],
            "GridPosition": [2.0, 1.0, 17.0, 8.0],
            "Status": ["Finished", "Finished", "Lapped", "Retired"],
            "Time": [seconds(19.207), seconds(4404.325), seconds(7.4), seconds(None)],
            "Points": [18.0, 25.0, 0.0, 0.0],
            "Laps": [53.0, 53.0, 52.0, 24.0],
        }
    )
    results = transform.results(raw)
    assert list(results["driver"]) == ["VER", "NOR", "COL", "ALO"]
    assert results["race_time_s"].tolist()[0] == pytest.approx(4404.325)
    assert results["gap_to_winner_s"].tolist()[1] == pytest.approx(19.207)
    assert results[["race_time_s", "gap_to_winner_s"]].iloc[2:].isna().all().all()  # a lapped car's "gap" is noise


def test_to_table_coerces_to_the_schema() -> None:
    frame = pd.DataFrame(
        {
            "time_utc": [datetime(2025, 9, 7, 12, 20)],  # naive: UTC by convention of FastF1
            "lap": [3.0],
            "category": ["Flag"],
            "message": ["GREEN LIGHT"],
            "status": [None],
            "flag": [""],
            "sector": [float("nan")],
            "driver_number": [None],
        }
    )
    table = transform.to_table(frame, schema.RACE_CONTROL_MESSAGES, season=2025, round=16, session="R")
    assert table.schema == schema.RACE_CONTROL_MESSAGES
    row = table.to_pylist()[0]
    assert (row["season"], row["round"], row["session"], row["lap"]) == (2025, 16, "R", 3)
    assert row["flag"] is None and row["sector"] is None and row["scope"] is None
    assert row["time_utc"].isoformat() == "2025-09-07T12:20:00+00:00"


def test_to_table_on_an_empty_frame() -> None:
    table = transform.to_table(pd.DataFrame(), schema.WEATHER, season=2025, round=1, session="R")
    assert table.num_rows == 0
    assert table.schema == schema.WEATHER


def test_standings_rows() -> None:
    standings = [
        {
            "position": "1",
            "positionText": "1",
            "points": "324",
            "wins": "7",
            "Driver": {"driverId": "piastri", "code": "PIA", "permanentNumber": "81"},
            "Constructors": [{"constructorId": "mclaren"}],
        }
    ]
    table = transform.to_table(
        transform.driver_standings_rows(standings), schema.DRIVER_STANDINGS, season=2025, round=16
    )
    assert table.to_pylist()[0] == {
        "season": 2025,
        "round": 16,
        "position": 1,
        "position_text": "1",
        "driver_id": "piastri",
        "driver": "PIA",
        "driver_number": "81",
        "points": 324.0,
        "wins": 7,
        "constructor_ids": ["mclaren"],
    }


def test_every_table_keys_first() -> None:
    for name, table_schema in schema.TABLES.items():
        key = ["season", "round"] if name in schema.ROUND_TABLES else ["season", "round", "session"]
        assert table_schema.names[: len(key)] == key, name
        assert all(not table_schema.field(column).nullable for column in key), name
        assert isinstance(table_schema, pa.Schema)
