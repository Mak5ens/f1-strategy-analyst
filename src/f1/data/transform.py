"""Turn FastF1 and OpenF1 data into the tables of `schema.py`. Pure functions: no network, no storage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa


def to_table(frame: pd.DataFrame, table_schema: pa.Schema, **key: int | str) -> pa.Table:
    """Add the key columns, coerce every column to its schema type, and build the Arrow table.

    Empty strings and NaN become nulls, float columns of whole numbers become integers, naive timestamps are UTC.
    """
    frame = frame.assign(**key)
    columns: dict[str, pd.Series[Any]] = {}
    for field in table_schema:
        column = frame[field.name] if field.name in frame.columns else pd.Series([None] * len(frame))
        columns[field.name] = _coerce(column.reset_index(drop=True), field.type)
    return pa.Table.from_pandas(pd.DataFrame(columns), schema=table_schema, preserve_index=False)


def _coerce(column: pd.Series[Any], arrow_type: pa.DataType) -> pd.Series[Any]:
    if pa.types.is_string(arrow_type):
        return column.astype(object).map(_text)
    if pa.types.is_integer(arrow_type):
        return pd.to_numeric(column, errors="coerce").round().astype("Int64")
    if pa.types.is_floating(arrow_type):
        return pd.to_numeric(column, errors="coerce").astype("float64")
    if pa.types.is_boolean(arrow_type):
        return column.astype("boolean")
    if pa.types.is_timestamp(arrow_type):
        stamps = pd.to_datetime(column)
        return stamps.dt.tz_localize("UTC") if stamps.dt.tz is None else stamps.dt.tz_convert("UTC")
    return column


def _text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return None
    text = str(value)
    return None if text in {"", "nan", "None", "NaT"} else text


def _seconds(column: pd.Series[Any]) -> pd.Series[Any]:
    if column.isna().all():  # pandas types an all-NaT column as datetime, not timedelta
        return pd.Series(np.nan, index=column.index, dtype="float64")
    return pd.to_timedelta(column).dt.total_seconds()


# FastF1 Laps column -> lake column; timedeltas become seconds.
_LAP_COLUMNS = {
    "Driver": "driver",
    "DriverNumber": "driver_number",
    "Team": "team",
    "LapNumber": "lap_number",
    "LapTime": "lap_time_s",
    "Sector1Time": "sector1_s",
    "Sector2Time": "sector2_s",
    "Sector3Time": "sector3_s",
    "LapStartTime": "lap_start_session_s",
    "Time": "lap_end_session_s",
    "Position": "position",
    "Stint": "stint",
    "Compound": "compound",
    "TyreLife": "tyre_life",
    "FreshTyre": "fresh_tyre",
    "PitInTime": "pit_in_session_s",
    "PitOutTime": "pit_out_session_s",
    "TrackStatus": "track_status",
    "IsAccurate": "is_accurate",
    "IsPersonalBest": "is_personal_best",
    "Deleted": "deleted",
    "DeletedReason": "deleted_reason",
    "FastF1Generated": "fastf1_generated",
}
_LAP_DURATIONS = [
    "lap_time_s",
    "sector1_s",
    "sector2_s",
    "sector3_s",
    "lap_start_session_s",
    "lap_end_session_s",
    "pit_in_session_s",
    "pit_out_session_s",
]


def laps(raw: pd.DataFrame) -> pd.DataFrame:
    """FastF1 `session.laps` with the lake's column names, sorted by driver and lap."""
    frame = pd.DataFrame(raw).reindex(columns=list(_LAP_COLUMNS)).rename(columns=_LAP_COLUMNS)
    for column in _LAP_DURATIONS:
        frame[column] = _seconds(frame[column])
    frame = frame.dropna(subset=["driver", "lap_number"])
    return frame.sort_values(["driver", "lap_number"]).reset_index(drop=True)


def stints(lap_frame: pd.DataFrame) -> pd.DataFrame:
    """One row per stint and driver, from the normalized laps."""
    timed = lap_frame.dropna(subset=["stint"]).sort_values(["driver", "lap_number"])
    grouped = timed.groupby(["driver", "stint"], sort=True)
    return grouped.agg(
        driver_number=("driver_number", "first"),
        team=("team", "first"),
        compound=("compound", "first"),
        fresh_tyre=("fresh_tyre", "first"),
        start_lap=("lap_number", "min"),
        end_lap=("lap_number", "max"),
        laps=("lap_number", "count"),
        tyre_life_start=("tyre_life", "first"),
        tyre_life_end=("tyre_life", "last"),
    ).reset_index()


def pit_stops(lap_frame: pd.DataFrame, openf1_pits: Sequence[Mapping[str, Any]] = ()) -> pd.DataFrame:
    """One row per pit stop: an in-lap followed by an out-lap.

    A driver who enters the pits and retires made no stop. OpenF1 adds the stationary time, and the pit lane time
    or the whole stop when FastF1 lacks it.
    """
    ordered = lap_frame.sort_values(["driver", "lap_number"])
    following = ordered.groupby("driver")[["lap_number", "pit_out_session_s"]].shift(-1)
    is_stop = (
        ordered["pit_in_session_s"].notna()
        & following["pit_out_session_s"].notna()
        & (following["lap_number"] == ordered["lap_number"] + 1)
    )
    fastf1_stops = pd.DataFrame(
        {
            "driver_number": ordered["driver_number"].astype(str),
            "lap": ordered["lap_number"].astype(int),
            "fastf1_lane_s": (following["pit_out_session_s"] - ordered["pit_in_session_s"]).round(3),
        }
    )[is_stop]

    openf1_stops = pd.DataFrame(
        [
            {
                "driver_number": str(pit["driver_number"]),
                "lap": int(pit["lap_number"]),
                "openf1_lane_s": pit.get("lane_duration", pit.get("pit_duration")),
                "stationary_time_s": pit.get("stop_duration"),
            }
            for pit in openf1_pits
            if pit.get("driver_number") is not None and pit.get("lap_number") is not None
        ],
        columns=["driver_number", "lap", "openf1_lane_s", "stationary_time_s"],
    )
    stops = fastf1_stops.merge(openf1_stops, on=["driver_number", "lap"], how="outer", indicator=True)
    stops["source"] = stops["_merge"].map({"left_only": "fastf1", "right_only": "openf1", "both": "fastf1+openf1"})
    stops["pit_lane_time_s"] = pd.to_numeric(stops["fastf1_lane_s"]).fillna(pd.to_numeric(stops["openf1_lane_s"]))

    by_lap = lap_frame.assign(driver_number=lap_frame["driver_number"].astype(str)).set_index(
        ["driver_number", "lap_number"]
    )
    drivers = lap_frame.assign(driver_number=lap_frame["driver_number"].astype(str)).drop_duplicates("driver_number")
    stops = stops.merge(drivers[["driver_number", "driver", "team"]], on="driver_number", how="inner")

    def lap_value(column: str, lap_offset: int) -> list[Any]:
        pairs = zip(stops["driver_number"], stops["lap"], strict=True)
        return [by_lap[column].get((number, lap + lap_offset)) for number, lap in pairs]

    stops["compound_before"] = lap_value("compound", 0)
    stops["compound_after"] = lap_value("compound", 1)
    stops["red_flag"] = [status is not None and "5" in str(status) for status in lap_value("track_status", 0)]
    stops = stops.sort_values(["driver", "lap"]).reset_index(drop=True)
    stops["stop_number"] = stops.groupby("driver").cumcount() + 1
    return stops


def race_control_messages(raw: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(raw).rename(
        columns={
            "Time": "time_utc",
            "Lap": "lap",
            "Category": "category",
            "Message": "message",
            "Status": "status",
            "Flag": "flag",
            "Scope": "scope",
            "Sector": "sector",
            "RacingNumber": "driver_number",
        }
    )
    return frame.sort_values("time_utc").reset_index(drop=True) if "time_utc" in frame else frame


def weather(raw: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(raw).rename(
        columns={
            "AirTemp": "air_temp_c",
            "TrackTemp": "track_temp_c",
            "Humidity": "humidity_pct",
            "Pressure": "pressure_mbar",
            "Rainfall": "rainfall",
            "WindSpeed": "wind_speed_ms",
            "WindDirection": "wind_direction_deg",
        }
    )
    if "Time" in frame:
        frame["session_time_s"] = _seconds(frame["Time"])
    return frame


def results(raw: pd.DataFrame) -> pd.DataFrame:
    """FastF1 gives the winner's race time and, for the others, a gap that only means something on the lead lap."""
    frame = pd.DataFrame(raw).rename(
        columns={
            "Abbreviation": "driver",
            "DriverNumber": "driver_number",
            "TeamName": "team",
            "DriverId": "driver_id",
            "FullName": "full_name",
            "TeamId": "team_id",
            "Position": "position",
            "ClassifiedPosition": "classified_position",
            "GridPosition": "grid_position",
            "Status": "status",
            "Points": "points",
            "Laps": "laps",
        }
    )
    time_s = _seconds(frame["Time"]) if "Time" in frame else pd.Series([None] * len(frame), index=frame.index)
    is_winner = frame["position"] == 1
    on_lead_lap = frame["status"] == "Finished"
    frame["race_time_s"] = time_s.where(is_winner)
    frame["gap_to_winner_s"] = time_s.where(on_lead_lap & ~is_winner)
    return frame.sort_values("position").reset_index(drop=True)


def driver_standings_rows(standings: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "position": entry.get("position"),
                "position_text": entry.get("positionText"),
                "driver_id": entry["Driver"]["driverId"],
                "driver": entry["Driver"].get("code"),
                "driver_number": entry["Driver"].get("permanentNumber"),
                "points": entry.get("points"),
                "wins": entry.get("wins"),
                "constructor_ids": [team["constructorId"] for team in entry.get("Constructors", [])],
            }
            for entry in standings
        ]
    )


def constructor_standings_rows(standings: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "position": entry.get("position"),
                "position_text": entry.get("positionText"),
                "constructor_id": entry["Constructor"]["constructorId"],
                "constructor_name": entry["Constructor"].get("name"),
                "points": entry.get("points"),
                "wins": entry.get("wins"),
            }
            for entry in standings
        ]
    )
