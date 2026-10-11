"""Schema of the race data lake: one Parquet table per entity, documented in docs/data-schema.md.

Every table starts with the columns of its key (season, round, and session for session tables). Durations are
float seconds, times of day are UTC timestamps, and a missing value is null, never 0 or an empty string.
Bump SCHEMA_VERSION on any change that breaks a reader: `just ingest` then rewrites the rounds stored with
an older version.
"""

import pyarrow as pa

SCHEMA_VERSION = 1

UTC_TIMESTAMP = pa.timestamp("us", tz="UTC")

ROUND_KEY = [
    pa.field("season", pa.int16(), nullable=False),
    pa.field("round", pa.int16(), nullable=False),
]
SESSION_KEY = [*ROUND_KEY, pa.field("session", pa.string(), nullable=False)]  # "R" race, "S" sprint

SESSIONS = pa.schema(
    [
        *SESSION_KEY,
        pa.field("session_name", pa.string()),
        pa.field("event_name", pa.string()),
        pa.field("official_event_name", pa.string()),
        pa.field("country", pa.string()),
        pa.field("location", pa.string()),
        pa.field("event_format", pa.string()),
        pa.field("start_utc", UTC_TIMESTAMP),
        pa.field("total_laps", pa.int16()),
        pa.field("session_key", pa.int32()),  # live timing key, also OpenF1's session_key
        pa.field("meeting_key", pa.int32()),
    ]
)

DRIVER = [
    pa.field("driver", pa.string(), nullable=False),  # three-letter code, e.g. LEC
    pa.field("driver_number", pa.string()),
    pa.field("team", pa.string()),
]

LAPS = pa.schema(
    [
        *SESSION_KEY,
        *DRIVER,
        pa.field("lap_number", pa.int16(), nullable=False),
        pa.field("lap_time_s", pa.float64()),
        pa.field("sector1_s", pa.float64()),
        pa.field("sector2_s", pa.float64()),
        pa.field("sector3_s", pa.float64()),
        pa.field("lap_start_session_s", pa.float64()),  # session time when the lap started
        pa.field("position", pa.int16()),  # at the end of the lap
        pa.field("stint", pa.int16()),
        pa.field("compound", pa.string()),
        pa.field("tyre_life", pa.int16()),  # laps on this set, this lap included
        pa.field("fresh_tyre", pa.bool_()),
        pa.field("pit_in_session_s", pa.float64()),
        pa.field("pit_out_session_s", pa.float64()),
        pa.field("track_status", pa.string()),  # every status seen during the lap, e.g. "14" (green, then SC)
        pa.field("is_accurate", pa.bool_()),
        pa.field("is_personal_best", pa.bool_()),
        pa.field("deleted", pa.bool_()),
        pa.field("deleted_reason", pa.string()),
        pa.field("fastf1_generated", pa.bool_()),
    ]
)

STINTS = pa.schema(
    [
        *SESSION_KEY,
        *DRIVER,
        pa.field("stint", pa.int16(), nullable=False),
        pa.field("compound", pa.string()),
        pa.field("fresh_tyre", pa.bool_()),
        pa.field("start_lap", pa.int16()),
        pa.field("end_lap", pa.int16()),
        pa.field("laps", pa.int16()),
        pa.field("tyre_life_start", pa.int16()),
        pa.field("tyre_life_end", pa.int16()),
    ]
)

PIT_STOPS = pa.schema(
    [
        *SESSION_KEY,
        *DRIVER,
        pa.field("stop_number", pa.int16(), nullable=False),
        pa.field("lap", pa.int16(), nullable=False),  # the in-lap
        pa.field("pit_lane_time_s", pa.float64()),  # pit entry to pit exit
        pa.field("stationary_time_s", pa.float64()),  # car stopped in the box (OpenF1)
        pa.field("compound_before", pa.string()),
        pa.field("compound_after", pa.string()),
        pa.field("red_flag", pa.bool_()),  # tyres changed while the race was stopped
        pa.field("source", pa.string()),  # "fastf1", "openf1" or "fastf1+openf1"
    ]
)

RACE_CONTROL_MESSAGES = pa.schema(
    [
        *SESSION_KEY,
        pa.field("time_utc", UTC_TIMESTAMP),
        pa.field("lap", pa.int16()),
        pa.field("category", pa.string()),
        pa.field("message", pa.string()),
        pa.field("status", pa.string()),
        pa.field("flag", pa.string()),
        pa.field("scope", pa.string()),
        pa.field("sector", pa.int16()),
        pa.field("driver_number", pa.string()),
    ]
)

WEATHER = pa.schema(
    [
        *SESSION_KEY,
        pa.field("session_time_s", pa.float64()),
        pa.field("air_temp_c", pa.float64()),
        pa.field("track_temp_c", pa.float64()),
        pa.field("humidity_pct", pa.float64()),
        pa.field("pressure_mbar", pa.float64()),
        pa.field("rainfall", pa.bool_()),
        pa.field("wind_speed_ms", pa.float64()),
        pa.field("wind_direction_deg", pa.int16()),
    ]
)

RESULTS = pa.schema(
    [
        *SESSION_KEY,
        *DRIVER,
        pa.field("driver_id", pa.string()),  # Jolpica-F1 id, e.g. leclerc
        pa.field("full_name", pa.string()),
        pa.field("team_id", pa.string()),
        pa.field("position", pa.int16()),
        pa.field("classified_position", pa.string()),  # a number, or R retired, D disqualified, W withdrawn...
        pa.field("grid_position", pa.int16()),  # 0 for a pit lane start
        pa.field("status", pa.string()),
        pa.field("points", pa.float64()),
        pa.field("laps", pa.int16()),
        pa.field("race_time_s", pa.float64()),  # the winner only
        pa.field("gap_to_winner_s", pa.float64()),  # finishers on the lead lap only
    ]
)

DRIVER_STANDINGS = pa.schema(
    [
        *ROUND_KEY,
        pa.field("position", pa.int16()),
        pa.field("position_text", pa.string()),
        pa.field("driver_id", pa.string(), nullable=False),
        pa.field("driver", pa.string()),
        pa.field("driver_number", pa.string()),
        pa.field("points", pa.float64()),
        pa.field("wins", pa.int16()),
        pa.field("constructor_ids", pa.list_(pa.string())),
    ]
)

CONSTRUCTOR_STANDINGS = pa.schema(
    [
        *ROUND_KEY,
        pa.field("position", pa.int16()),
        pa.field("position_text", pa.string()),
        pa.field("constructor_id", pa.string(), nullable=False),
        pa.field("constructor_name", pa.string()),
        pa.field("points", pa.float64()),
        pa.field("wins", pa.int16()),
    ]
)

# Tables written once per session of a round, then once per round.
SESSION_TABLES: dict[str, pa.Schema] = {
    "sessions": SESSIONS,
    "laps": LAPS,
    "stints": STINTS,
    "pit_stops": PIT_STOPS,
    "race_control_messages": RACE_CONTROL_MESSAGES,
    "weather": WEATHER,
    "results": RESULTS,
}
ROUND_TABLES: dict[str, pa.Schema] = {
    "driver_standings": DRIVER_STANDINGS,
    "constructor_standings": CONSTRUCTOR_STANDINGS,
}
TABLES: dict[str, pa.Schema] = {**SESSION_TABLES, **ROUND_TABLES}
