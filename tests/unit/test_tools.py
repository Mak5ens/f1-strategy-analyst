"""The race analysis tools on a synthetic 10-lap race whose every number can be checked by hand.

VER stops on lap 3 (out-lap 4), LEC on lap 5 (out-lap 6). Lap times, so lap end times, are chosen so that:
gaps LEC minus VER at the line, laps 1 to 10: 1.0, 1.5, 0.0, -13.5, -11.0, 3.5, 3.0, 2.5, 2.0, 1.5.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from core.lake import Lake, LakeSettings
from core.tools import ToolError
from f1.data import connect, schema, transform
from f1.tools import RaceData, catalog
from f1.tools.neutralizations import find_periods

KEY: dict[str, int | str] = {"season": 2025, "round": 1, "session": "R"}
SESSION_START = 1000.0
LAP_TIMES: dict[str, list[float]] = {
    "VER": [95, 90, 92, 104, 90, 90, 90, 90, 90, 90],
    "LEC": [96, 90.5, 90.5, 90.5, 92.5, 104.5, 89.5, 89.5, 89.5, 89.5],
}
STOP_LAP = {"VER": 3, "LEC": 5}


def race_laps() -> pd.DataFrame:
    rows = []
    for driver, times in LAP_TIMES.items():
        end = SESSION_START
        stop = STOP_LAP[driver]
        for lap, lap_time in enumerate(times, start=1):
            start, end = end, end + lap_time
            rows.append(
                {
                    "driver": driver,
                    "driver_number": "1" if driver == "VER" else "16",
                    "lap_number": lap,
                    "lap_time_s": lap_time,
                    "lap_start_session_s": start,
                    "lap_end_session_s": end,
                    "stint": 1 if lap <= stop else 2,
                    "compound": "MEDIUM" if lap <= stop else "HARD",
                    "tyre_life": lap if lap <= stop else lap - stop,
                    "pit_in_session_s": end - 5 if lap == stop else None,
                    "pit_out_session_s": start + 5 if lap == stop + 1 else None,
                    "track_status": "1",
                    "deleted": False,
                }
            )
    frame = pd.DataFrame(rows)
    # Positions from the gaps: LEC leads only while VER's stop puts him behind (laps 4 and 5).
    leader = {lap: "LEC" if lap in (4, 5) else "VER" for lap in range(1, 11)}
    frame["position"] = [
        1 if leader[lap] == driver else 2 for driver, lap in zip(frame.driver, frame.lap_number, strict=True)
    ]
    return frame


def race_pit_stops() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"driver": "VER", "stop_number": 1, "lap": 3, "pit_lane_time_s": 20.0, "stationary_time_s": 2.5,
             "compound_before": "MEDIUM", "compound_after": "HARD", "red_flag": False, "source": "fastf1+openf1"},
            {"driver": "LEC", "stop_number": 1, "lap": 5, "pit_lane_time_s": 20.5, "stationary_time_s": 2.8,
             "compound_before": "MEDIUM", "compound_after": "HARD", "red_flag": False, "source": "fastf1+openf1"},
        ]
    )  # fmt: skip


T0 = datetime(2025, 3, 16, 4, 0, tzinfo=UTC)


def message(minute: int, lap: int, text: str, *, category: str = "Other", status: str | None = None,
            flag: str | None = None) -> dict[str, Any]:  # fmt: skip
    return {"time_utc": T0 + timedelta(minutes=minute), "lap": lap, "category": category, "message": text,
            "status": status, "flag": flag}  # fmt: skip


MESSAGES = [
    message(0, 1, "GREEN LIGHT - PIT EXIT OPEN", category="Flag", flag="GREEN"),
    message(10, 2, "SAFETY CAR DEPLOYED", category="SafetyCar", status="DEPLOYED"),
    message(11, 2, "SAFETY CAR DEPLOYED", category="SafetyCar", status="DEPLOYED"),  # repeated: ignored
    message(16, 4, "SAFETY CAR IN THIS LAP", category="SafetyCar", status="IN THIS LAP"),
    message(30, 7, "VSC DEPLOYED", category="SafetyCar", status="DEPLOYED"),
    message(32, 7, "VSC ENDING", category="SafetyCar", status="ENDING"),
    message(40, 8, "SAFETY CAR DEPLOYED", category="SafetyCar", status="DEPLOYED"),
    message(42, 8, "RED FLAG", category="Flag", flag="RED"),  # closes the safety car
    message(60, 8, "ROLLING START PROCEDURE"),
    message(62, 9, "ROLLING START"),
    message(70, 10, "SAFETY CAR DEPLOYED", category="SafetyCar", status="DEPLOYED"),
    message(75, 10, "CHEQUERED FLAG", category="Flag", flag="CHEQUERED"),  # finishes under safety car
]


@pytest.fixture(scope="module")
def tools(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    lake = Lake(LakeSettings(uri=str(tmp_path_factory.mktemp("lake")), _env_file=None))
    tables = {
        "laps": (race_laps(), schema.LAPS),
        "pit_stops": (race_pit_stops(), schema.PIT_STOPS),
        "race_control_messages": (pd.DataFrame(MESSAGES), schema.RACE_CONTROL_MESSAGES),
        "sessions": (
            pd.DataFrame([{"event_name": "Australian Grand Prix", "location": "Melbourne", "country": "Australia",
                           "start_utc": T0}]),
            schema.SESSIONS,
        ),
        "results": (
            pd.DataFrame([{"driver": "VER", "full_name": "Max Verstappen", "team": "Red Bull Racing", "position": 1},
                          {"driver": "LEC", "full_name": "Charles Leclerc", "team": "Ferrari", "position": 2}]),
            schema.RESULTS,
        ),
    }  # fmt: skip
    for name, (frame, table_schema) in tables.items():
        lake.write_parquet(f"{name}/2025/01-R.parquet", transform.to_table(frame, table_schema, **KEY))
    return {tool.name: tool for tool in catalog(RaceData(connect(lake)))}


def run(tools: dict[str, Any], name: str, **arguments: Any) -> dict[str, Any]:
    result: dict[str, Any] = tools[name].run({"season": 2025, "round": 1, **arguments}).model_dump()
    return result


def test_gap_between_drivers(tools: dict[str, Any]) -> None:
    result = run(tools, "gap_between_drivers", driver="lec", reference_driver="VER")
    assert [lap["gap_s"] for lap in result["laps"]] == [1.0, 1.5, 0.0, -13.5, -11.0, 3.5, 3.0, 2.5, 2.0, 1.5]
    assert result["laps"][1]["lap_delta_s"] == 0.5
    assert result["laps"][0]["lap_delta_s"] is None
    assert (result["first_gap_s"], result["final_gap_s"], result["gained_s"]) == (1.0, 1.5, -0.5)
    assert (result["laps"][3]["position"], result["laps"][3]["reference_position"]) == (1, 2)


def test_gap_on_a_lap_range(tools: dict[str, Any]) -> None:
    result = run(tools, "gap_between_drivers", driver="LEC", reference_driver="VER", from_lap=7, to_lap=9)
    assert [lap["lap"] for lap in result["laps"]] == [7, 8, 9]
    assert result["gained_s"] == 1.0


def test_pit_stop_loss(tools: dict[str, Any]) -> None:
    (stop,) = run(tools, "pit_stop_loss", driver="VER")["stops"]
    # Laps 3 and 4 took 92 + 104 = 196 s; normal laps around the stop are 90 s.
    assert stop["in_and_out_laps_s"] == 196.0
    assert stop["reference_lap_s"] == 90.0
    assert stop["time_lost_s"] == 16.0
    assert (stop["pit_lane_time_s"], stop["stationary_time_s"]) == (20.0, 2.5)
    assert stop["reference_laps"] == 6  # lap 2 before; laps 5 to 9 after. Lap 1 is the standing start
    assert not stop["neutralized"]


def test_pit_cycle_overcut_that_failed(tools: dict[str, Any]) -> None:
    result = run(tools, "pit_cycle", driver="LEC", rival="VER")
    assert (result["first_to_stop"], result["ahead_after"], result["outcome"]) == ("VER", "VER", "order_held")
    assert result["summary"].startswith("VER stayed ahead of LEC: LEC's overcut (stopped later)")
    assert (result["lap_before"], result["lap_after"]) == (2, 6)
    assert (result["gap_before_s"], result["gap_after_s"], result["gained_s"]) == (1.5, 3.5, -2.0)
    assert not result["driver_passed_rival"] and not result["rival_passed_driver"]


def test_pit_cycle_from_the_other_side(tools: dict[str, Any]) -> None:
    result = run(tools, "pit_cycle", driver="VER", rival="LEC")
    assert (result["first_to_stop"], result["outcome"]) == ("VER", "order_held")
    assert result["gained_s"] == 2.0


def test_neutralizations(tools: dict[str, Any]) -> None:
    result = run(tools, "neutralizations")
    periods = [(p["kind"], p["start_lap"], p["end_lap"], p["ended_by_finish"]) for p in result["periods"]]
    assert periods == [
        ("safety_car", 2, 4, False),
        ("virtual_safety_car", 7, 7, False),
        ("safety_car", 8, 8, False),
        ("red_flag", 8, 9, False),
        ("safety_car", 10, 10, True),
    ]
    assert (result["safety_cars"], result["virtual_safety_cars"], result["red_flags"]) == (3, 1, 1)
    assert result["periods"][0]["duration_s"] == 360.0
    assert result["periods"][0]["start_utc"].tzinfo is not None


def test_a_safety_car_deployed_after_a_red_flag_ends_it() -> None:
    restart_behind_safety_car = [
        message(0, 5, "RED FLAG", category="Flag", flag="RED"),
        message(20, 5, "SAFETY CAR DEPLOYED", category="SafetyCar", status="DEPLOYED"),
        message(25, 7, "SAFETY CAR IN THIS LAP", category="SafetyCar", status="IN THIS LAP"),
    ]
    periods = find_periods(restart_behind_safety_car)
    assert [(p.kind, p.start_lap, p.end_lap) for p in periods] == [("red_flag", 5, 5), ("safety_car", 5, 7)]


def test_stint_degradation_removes_the_fuel_effect(tmp_path: Path) -> None:
    # One 15-lap stint from lap 2: 0.1 s per lap of tyre age, minus 0.06 s per lap of fuel burnt.
    laps: list[dict[str, Any]] = [
        {"driver": "HAM", "lap_number": lap, "stint": 1, "compound": "HARD", "tyre_life": lap,
         "lap_time_s": 90 + 0.1 * lap - 0.06 * (lap - 1), "track_status": "1", "deleted": False}
        for lap in range(1, 17)
    ]  # fmt: skip
    laps[9]["lap_time_s"] += 5  # stuck in traffic
    laps[11]["track_status"] = "126"  # a VSC during the lap
    laps[15]["pit_in_session_s"] = 9999.0  # in-lap
    lake = Lake(LakeSettings(uri=str(tmp_path / "lake"), _env_file=None))
    lake.write_parquet("laps/2025/01-R.parquet", transform.to_table(pd.DataFrame(laps), schema.LAPS, **KEY))
    tools = {tool.name: tool for tool in catalog(RaceData(connect(lake)))}

    (stint,) = run(tools, "stint_degradation", driver="HAM")["stints"]
    assert stint["degradation_s_per_lap"] == pytest.approx(0.1, abs=1e-4)
    assert stint["raw_slope_s_per_lap"] == pytest.approx(0.04, abs=1e-4)
    assert stint["r_squared"] == pytest.approx(1.0)
    assert stint["laps_used"] == 12
    assert stint["excluded"] == {"standing start": 1, "slow outlier": 1, "not green flag": 1, "in or out lap": 1}


def test_stint_degradation_needs_enough_laps(tools: dict[str, Any]) -> None:
    stints = run(tools, "stint_degradation", driver="VER")["stints"]
    assert stints[0]["degradation_s_per_lap"] is None
    assert "clean laps" in stints[0]["note"]


@pytest.mark.parametrize(
    ("name", "arguments", "message_part"),
    [
        ("gap_between_drivers", {"driver": "HAM", "reference_driver": "VER"}, "Drivers: LEC, VER"),
        ("gap_between_drivers", {"driver": "VER", "reference_driver": "VER"}, "must differ"),
        ("pit_stop_loss", {"driver": "VER", "stop_number": 2}, "made no stop 2"),
        ("pit_cycle", {"driver": "VER", "rival": "LEC", "rival_stop": 3}, "no stop 3"),
        ("stint_degradation", {"driver": "VER", "stint": 4}, "no stint 4"),
        ("neutralizations", {"round": 2}, "No race control messages"),
    ],
)
def test_errors_say_what_is_missing(
    tools: dict[str, Any], name: str, arguments: dict[str, Any], message_part: str
) -> None:
    with pytest.raises(ToolError, match=message_part):
        run(tools, name, **arguments)


def test_invalid_arguments_are_refused_before_computing(tools: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="driver"):
        run(tools, "pit_stop_loss", driver="Verstappen")


def test_catalog_for_tool_calling(tools: dict[str, Any]) -> None:
    assert list(tools) == [
        "find_race",
        "session_result",
        "gap_between_drivers",
        "stint_degradation",
        "pit_stop_loss",
        "pit_cycle",
        "neutralizations",
    ]
    for tool in tools.values():
        spec = tool.openai_schema()
        assert spec["function"]["name"] == tool.name
        parameters = spec["function"]["parameters"]
        if tool.name == "find_race":  # names a race: the others take the round it gives
            assert set(parameters["required"]) == {"season", "grand_prix"}
            continue
        if tool.name == "session_result":  # qualifying too
            assert parameters["properties"]["session"]["enum"] == ["R", "S", "Q", "SQ"]
            continue
        assert {"season", "round"} <= set(parameters["required"])
        assert parameters["properties"]["session"]["enum"] == ["R", "S"]


@pytest.mark.parametrize("name", ["Australian Grand Prix", "Australie", "Grand Prix d'Australie", "Melbourne"])
def test_find_race_reads_the_round_and_the_drivers(tools: dict[str, Any], name: str) -> None:
    result = tools["find_race"].run({"season": 2025, "grand_prix": name}).model_dump()
    assert (result["round"], result["event"], result["sessions"]) == (1, "Australian Grand Prix", ["R"])
    assert result["drivers"][0] == {"code": "VER", "name": "Max Verstappen", "team": "Red Bull Racing"}


def test_find_race_lists_the_grands_prix_when_it_finds_none(tools: dict[str, Any]) -> None:
    with pytest.raises(ToolError, match="Grands Prix: Australian Grand Prix"):
        tools["find_race"].run({"season": 2025, "grand_prix": "Lune"})
    with pytest.raises(ToolError, match="No race of 2024"):
        tools["find_race"].run({"season": 2024, "grand_prix": "Australie"})


def test_session_result_reads_the_classification_and_the_fastest_lap(tools: dict[str, Any]) -> None:
    result = run(tools, "session_result")
    first, second = result["classification"]
    assert (first["driver"], first["name"], first["position"]) == ("VER", "Max Verstappen", "1")
    assert (second["driver"], second["q3_s"]) == ("LEC", None)
    # The fastest lap of the synthetic race: LEC's 89.5 s on lap 7, the first of his four.
    assert result["fastest_lap"] == {"driver": "LEC", "name": "Charles Leclerc", "lap": 7, "lap_time_s": 89.5}


def test_session_result_of_a_session_not_ingested(tools: dict[str, Any]) -> None:
    with pytest.raises(ToolError, match="find_race lists the sessions"):
        run(tools, "session_result", session="Q")
