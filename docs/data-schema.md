# Race data schema

The agent never fetches data while it answers a question: `just ingest` loads it beforehand into a lake of Parquet files, and the tools query it with DuckDB.
This page is the contract between the ingestion (`src/f1/data/`) and its readers: the deterministic tools (LAB-144), the test set (LAB-146) and the season benchmark of llmops-platform (LAB-139).
The Arrow schemas in [`src/f1/data/schema.py`](../src/f1/data/schema.py) are the source of truth; this page explains them.

## Sources

| Source | What it gives | Limits |
| -- | -- | -- |
| [FastF1](https://docs.fastf1.dev/) (official live timing archive) | Schedule, laps, stints, pit lane times, results, race control messages, weather | 500 calls per hour, enforced by FastF1 itself; HTTP cache on disk in `.cache/fastf1` |
| [OpenF1](https://openf1.org/) | Stationary time of each pit stop; pit stops FastF1 missed | Free tier, a few calls per second; the client spaces calls by 0.5 s |
| [Jolpica-F1](https://github.com/jolpica/jolpica-f1) (successor of Ergast) | Championship standings after each round | 4 calls per second, 500 per hour |

Scope: seasons 2024 to 2026, races and sprints.
2026 opens a new technical regulation, which makes it a good test of whether the tools generalize.

## Storage

Files live in an S3 bucket (SeaweedFS from `compose.yaml` locally, `LAKE_URI=s3://race-data`), or in a local folder when `LAKE_URI` is a path.
One folder per table, one file per session (or per round for the standings):

```text
laps/2025/16-R.parquet                  # round 16, race
laps/2025/19-S.parquet                  # round 19, sprint
driver_standings/2025/16.parquet        # standings after round 16
_manifest/2025/16.json                  # written last: the round is complete
```

`f1.data.connect()` returns a DuckDB connection with one view per table over `<table>/**/*.parquet`:

```python
from f1.data import connect

connect().sql("SELECT driver, lap, pit_lane_time_s FROM pit_stops WHERE season = 2025 AND round = 16")
```

From the shell: `just sql "SELECT * FROM results WHERE season = 2025 AND round = 16"`.

## Idempotence and resumption

A round is the unit of work.
Its sessions and standings are fetched first, then written, then the manifest is written last.
`just ingest` skips any round whose manifest carries the current `SCHEMA_VERSION`, so a rerun only fetches what is missing.
A round that failed (network, data not published yet) has no manifest and is fetched again on the next run; its files are overwritten by key, never appended, so nothing is duplicated.
When FastF1's rate limit is reached, the run pauses 15 minutes and resumes the round, up to 8 times.
Rounds whose last session ended less than 6 hours ago are reported `not_ready`.

`--force` rewrites stored rounds; FastF1's HTTP cache makes it fast.
Bump `SCHEMA_VERSION` on any change that breaks a reader: the next `just ingest` rewrites every round.

## Conventions

- Every table starts with its key: `season`, `round`, and `session` (`R` race, `S` sprint) for session tables.
- `driver` is the three-letter code (`LEC`); `driver_number` is a string, as in the sources; `driver_id` is Jolpica's (`leclerc`) and joins the standings.
- Durations are float seconds (`_s`), times within a session are seconds since the session clock started (`_session_s`), and times of day are UTC timestamps (`_utc`).
- A missing value is null, never 0 or an empty string.

## Tables

### sessions

One row per session: `session_name`, `event_name`, `official_event_name`, `country`, `location`, `event_format` (`conventional`, `sprint_qualifying`...), `start_utc`, `total_laps` (scheduled), `session_key` and `meeting_key` (live timing keys, also OpenF1's).

### laps

One row per lap and driver, from FastF1.

| Column | Meaning |
| -- | -- |
| `lap_number`, `lap_time_s`, `sector1_s` to `sector3_s` | Null when the timing missed it (often lap 1, in and out laps) |
| `lap_start_session_s`, `lap_end_session_s` | Session time when the lap started and ended. The gap between two drivers at the end of lap n is the difference of their `lap_end_session_s`: it stays right when a lap time is missing |
| `position` | Position at the end of the lap |
| `stint`, `compound`, `tyre_life`, `fresh_tyre` | Tyres: `tyre_life` counts the laps on this set, this lap included, earlier sessions too |
| `pit_in_session_s`, `pit_out_session_s` | Set on the in-lap and the out-lap |
| `track_status` | Every status seen during the lap: `1` green, `2` yellow, `4` safety car, `5` red flag, `6` VSC, `7` VSC ending. `"14"` means green then safety car |
| `is_accurate` | FastF1's check that the lap time can be trusted for pace comparisons |
| `deleted`, `deleted_reason` | Lap time deleted by the stewards (track limits) |
| `fastf1_generated` | Lap added by FastF1 to complete a driver's race (crash, retirement) |

### stints

One row per stint and driver, derived from the laps: `compound`, `fresh_tyre`, `start_lap`, `end_lap`, `laps`, `tyre_life_start`, `tyre_life_end`.

### pit_stops

One row per stop: an in-lap followed by an out-lap.
A pit lane start and a retirement into the pits are not stops.

| Column | Meaning |
| -- | -- |
| `stop_number`, `lap` | `lap` is the in-lap |
| `pit_lane_time_s` | Pit entry to pit exit, from FastF1's timing; OpenF1's when FastF1 lacks it |
| `stationary_time_s` | Car stopped in the box, from OpenF1 (null before 2023 and when OpenF1 lacks it) |
| `compound_before`, `compound_after` | Tyres of the in-lap and of the out-lap |
| `red_flag` | The in-lap saw a red flag: tyres changed while the race was stopped, not a strategic stop |
| `source` | `fastf1`, `openf1`, or `fastf1+openf1` when both saw it |

Checked against Jolpica-F1: the 840 stops of the 24 races of 2025 match driver by driver.

### race_control_messages

Every message of race control: `time_utc`, `lap`, `category` (`Flag`, `SafetyCar`, `Drs`, `Other`...), `message`, `status`, `flag`, `scope`, `sector`, `driver_number`.
Penalties and investigations are `Other` messages starting with `FIA STEWARDS:`.

### weather

One row per minute: `session_time_s`, `air_temp_c`, `track_temp_c`, `humidity_pct`, `pressure_mbar`, `rainfall`, `wind_speed_ms`, `wind_direction_deg`.

### results

Classification of the session: `position`, `classified_position` (a number, or `R` retired, `D` disqualified, `E` excluded, `W` withdrawn, `F` failed to qualify, `N` not classified), `grid_position` (0 for a pit lane start), `status`, `points`, `laps`, `driver_id`, `full_name`, `team_id`.
`race_time_s` is set for the winner only, and `gap_to_winner_s` for the other finishers on the lead lap only: for lapped cars, FastF1's time is not a gap.

### driver_standings, constructor_standings

The championship after each round, from Jolpica-F1: `position`, `position_text`, `points`, `wins`, plus `driver_id`, `driver`, `driver_number` and `constructor_ids` (a list: a driver can change team during a season), or `constructor_id` and `constructor_name`.
