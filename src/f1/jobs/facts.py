"""The facts of one session, computed from the lake: the model writes the summary from them, it computes nothing.

Each kind of session has its own facts:
- practice: the order of the best laps, the gaps to the fastest and to the car ahead, laps done, and the longest
  run on one set of tyres;
- qualifying (and sprint qualifying): the order, each part's time, the gaps to pole and to the car ahead, who went
  out in Q1 or Q2;
- race (and sprint): the result, grid and places gained, pit stops and tyres, the fastest lap, the neutralizations.
All of them also get the weather and the red flags. Drivers are named in full, from the results ("Andrea Kimi
Antonelli", never "ANT"): given a code, a model expands it from memory, and wrongly. Lap times are written as on a
timing screen ("1:18.792"), a race time with its hours, other durations in seconds with three decimals.
"""

from statistics import median
from typing import Any

import duckdb

from f1.tools.data import is_clean, number
from f1.tools.neutralizations import find_periods

SESSION_NAMES = {
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
    "SQ": "Sprint Qualifying",
    "Q": "Qualifying",
    "S": "Sprint",
    "R": "Race",
}
PRACTICE, QUALIFYING, RACE = {"FP1", "FP2", "FP3"}, {"SQ", "Q"}, {"S", "R"}
# A run says something about race pace from this many clean laps on one set of tyres, each within this share of the
# driver's best lap: in practice, a driver alternates push laps and slow laps to cool the tyres, both on green.
LONG_RUN_LAPS = 5
RUN_PACE = 1.12


class NoSessionData(LookupError):
    """The session is not in the lake."""


def lap_time(seconds: float | None) -> str | None:
    """1:18.792, as on a timing screen; 1:42:06.304 for a race."""
    if seconds is None:
        return None
    minutes, rest = divmod(round(seconds, 3), 60)
    if minutes < 60:
        return f"{int(minutes)}:{rest:06.3f}"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}:{int(minutes):02d}:{rest:06.3f}"


def session_facts(db: duckdb.DuckDBPyConnection, season: int, round_number: int, code: str) -> dict[str, Any]:
    key = [season, round_number, code]
    info = _rows(db, "SELECT event_name, location, country, total_laps FROM sessions WHERE {key}", key)
    if not info:
        raise NoSessionData(f"{season} round {round_number} {code} is not in the lake: run `just ingest {season}`")
    facts: dict[str, Any] = {
        "season": season,
        "round": round_number,
        "event": info[0]["event_name"],
        "location": info[0]["location"],
        "session": SESSION_NAMES[code],
        "weather": _weather(db, key),
    }
    messages = _rows(db, "SELECT * FROM race_control_messages WHERE {key} ORDER BY time_utc", key)
    names = dict(
        db.execute(
            "SELECT driver, full_name FROM results WHERE season = ? AND round = ? AND session = ? "
            "AND full_name IS NOT NULL",
            key,
        ).fetchall()
    )
    if code in RACE:
        facts["scheduled_laps"] = info[0]["total_laps"]
        facts.update(_race(db, key, messages))
    else:
        facts["red_flags"] = sum(message["flag"] == "RED" for message in messages)
        facts.update(_qualifying(db, key) if code in QUALIFYING else _practice(db, key))
    for entry in facts["classification"]:
        entry["driver"] = names.get(entry["driver"], entry["driver"])
    if facts.get("fastest_lap"):
        facts["fastest_lap"]["driver"] = names.get(facts["fastest_lap"]["driver"], facts["fastest_lap"]["driver"])
    return facts


def _practice(db: duckdb.DuckDBPyConnection, key: list[Any]) -> dict[str, Any]:
    laps = _rows(db, "SELECT * FROM laps WHERE {key} ORDER BY driver, lap_number", key)
    drivers: dict[str, list[dict[str, Any]]] = {}
    for lap in laps:
        drivers.setdefault(str(lap["driver"]), []).append(lap)
    best = {
        driver: min((lap for lap in own if _timed(lap)), key=lambda lap: lap["lap_time_s"], default=None)
        for driver, own in drivers.items()
    }
    fastest = min((lap["lap_time_s"] for lap in best.values() if lap), default=None)
    classification = []
    ahead: float | None = None
    ranked = sorted(best.items(), key=lambda item: item[1]["lap_time_s"] if item[1] else float("inf"))
    for position, (driver, best_lap) in enumerate(ranked, start=1):
        own = drivers[driver]
        entry: dict[str, Any] = {"driver": driver, "team": own[0]["team"], "laps": len(own)}
        if best_lap and fastest is not None:
            entry = {"position": position, **entry}
            entry |= {
                "best_lap": lap_time(best_lap["lap_time_s"]),
                "gap_to_fastest_s": round(best_lap["lap_time_s"] - fastest, 3),
                "gap_to_ahead_s": round(best_lap["lap_time_s"] - ahead, 3) if ahead is not None else None,
                "best_lap_compound": best_lap["compound"],
            }
            ahead = best_lap["lap_time_s"]
        if best_lap and (run := _longest_run(own, slowest=best_lap["lap_time_s"] * RUN_PACE)):
            entry["longest_run"] = run
        classification.append(entry)
    return {"classification": classification}


def _longest_run(laps: list[dict[str, Any]], *, slowest: float) -> dict[str, Any] | None:
    """The stint with the most clean laps at pace (no slower than `slowest`), if it has enough to say something
    about race pace."""
    stints: dict[int, list[dict[str, Any]]] = {}
    for lap in laps:
        if is_clean(lap) and number(lap["stint"]) is not None and lap["lap_time_s"] <= slowest:
            stints.setdefault(int(lap["stint"]), []).append(lap)
    clean = max(stints.values(), key=len, default=[])
    if len(clean) < LONG_RUN_LAPS:
        return None
    return {
        "compound": clean[0]["compound"],
        "clean_laps": len(clean),
        "median_lap": lap_time(median(lap["lap_time_s"] for lap in clean)),
    }


def _qualifying(db: duckdb.DuckDBPyConnection, key: list[Any]) -> dict[str, Any]:
    results = _rows(db, "SELECT * FROM results WHERE {key} ORDER BY position NULLS LAST", key)
    deleted = dict(
        db.execute(
            "SELECT driver, count(*) FROM laps WHERE season = ? AND round = ? AND session = ? AND deleted "
            "GROUP BY driver",
            key,
        ).fetchall()
    )
    times = {row["driver"]: _best_part(row) for row in results}
    pole = times[results[0]["driver"]] if results else None
    order = []
    ahead: float | None = None
    for row in results:
        parts = {part: number(row[f"{part}_s"]) for part in ("q1", "q2", "q3")}
        entry: dict[str, Any] = {"position": _int(row["position"]), "driver": row["driver"], "team": row["team"]}
        entry |= {part: lap_time(seconds) for part, seconds in parts.items() if seconds is not None}
        best = times[row["driver"]]
        if best is not None and pole is not None:
            entry["gap_to_pole_s"] = round(best - pole, 3)
            if ahead is not None:
                entry["gap_to_ahead_s"] = round(best - ahead, 3)
            ahead = best
        entry["out_in"] = "Q1" if parts["q2"] is None else "Q2" if parts["q3"] is None else None
        if deleted.get(row["driver"]):
            entry["laps_deleted"] = int(deleted[row["driver"]])
        order.append(entry)
    return {"classification": order}


def _best_part(row: dict[str, Any]) -> float | None:
    """The time that ranks a driver: the last part he set a time in."""
    for part in ("q3_s", "q2_s", "q1_s"):
        if (seconds := number(row[part])) is not None:
            return seconds
    return None


def _race(db: duckdb.DuckDBPyConnection, key: list[Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    results = _rows(db, "SELECT * FROM results WHERE {key} ORDER BY position NULLS LAST", key)
    stints: dict[str, list[str]] = {}
    for row in _rows(db, "SELECT driver, compound FROM stints WHERE {key} ORDER BY driver, stint", key):
        stints.setdefault(str(row["driver"]), []).append(str(row["compound"]))
    stops: dict[str, int] = dict(
        db.execute(
            "SELECT driver, count(*) FROM pit_stops WHERE season = ? AND round = ? AND session = ? AND NOT red_flag "
            "GROUP BY driver",
            key,
        ).fetchall()
    )
    classification = []
    for row in results:
        grid, position = _int(row["grid_position"]), _int(row["position"])
        entry: dict[str, Any] = {
            "position": row["classified_position"],
            "driver": row["driver"],
            "team": row["team"],
            "grid": "pit lane" if grid == 0 else grid,
            "status": row["status"],
        }
        if grid and position:
            entry["places_gained"] = grid - position
        if (gap := number(row["gap_to_winner_s"])) is not None:
            entry["gap_to_winner_s"] = round(gap, 3)
        if (total := number(row["race_time_s"])) is not None:
            entry["race_time"] = lap_time(total)
        entry["pit_stops"] = int(stops.get(row["driver"], 0))
        entry["tyres"] = stints.get(str(row["driver"]), [])
        classification.append(entry)
    fastest = _rows(
        db,
        "SELECT driver, lap_number, lap_time_s FROM laps WHERE {key} AND lap_time_s IS NOT NULL "
        "AND NOT coalesce(deleted, false) ORDER BY lap_time_s LIMIT 1",
        key,
    )
    periods = find_periods(messages) if messages else []
    return {
        "classification": classification,
        "fastest_lap": {
            "driver": fastest[0]["driver"],
            "lap": int(fastest[0]["lap_number"]),
            "time": lap_time(fastest[0]["lap_time_s"]),
        }
        if fastest
        else None,
        "neutralizations": [
            {"kind": period.kind, "from_lap": period.start_lap, "to_lap": period.end_lap} for period in periods
        ],
    }


def _weather(db: duckdb.DuckDBPyConnection, key: list[Any]) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT min(air_temp_c), max(air_temp_c), min(track_temp_c), max(track_temp_c), bool_or(rainfall) "
        "FROM weather WHERE season = ? AND round = ? AND session = ?",
        key,
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return {
        "air_temp_c": [round(row[0], 1), round(row[1], 1)],
        "track_temp_c": [round(row[2], 1), round(row[3], 1)],
        "rain": bool(row[4]),
    }


def _rows(db: duckdb.DuckDBPyConnection, query: str, key: list[Any]) -> list[dict[str, Any]]:
    sql = query.replace("{key}", "season = ? AND round = ? AND session = ?")
    rows: list[dict[str, Any]] = db.execute(sql, key).df().to_dict("records")  # type: ignore[assignment]
    return rows


def _timed(lap: dict[str, Any]) -> bool:
    return number(lap["lap_time_s"]) is not None and not lap["deleted"]


def _int(value: object) -> int | None:
    seconds = number(value)
    return None if seconds is None else int(seconds)
