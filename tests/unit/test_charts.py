"""The chart of each analysis a debrief cites (LAB-189): read by code from the tool, never guessed."""

from typing import Any

from core.agent.state import Result
from f1.charts import FactChart, chart_for


def result(tool: str, arguments: dict[str, Any], output: dict[str, Any] | None, error: str | None = None) -> Result:
    return Result(id="x", tool=tool, label="x", arguments=arguments, output=output, error=error)


def test_a_gap_and_a_pit_cycle_show_the_gaps_to_the_other_driver_over_their_laps() -> None:
    gap = result("gap_between_drivers", {"driver": "LEC", "reference_driver": "VER"},
                 {"laps": [{"lap": 10}, {"lap": 11}, {"lap": 25}]})  # fmt: skip
    assert chart_for(gap) == FactChart(kind="gaps", drivers=["LEC", "VER"], reference="VER", from_lap=10, to_lap=25)

    cycle = result("pit_cycle", {"driver": "LEC", "rival": "PIA"},
                   {"driver": "LEC", "rival": "PIA", "lap_before": 2, "lap_after": 22})  # fmt: skip
    assert chart_for(cycle) == FactChart(kind="gaps", drivers=["LEC", "PIA"], reference="PIA", from_lap=1, to_lap=25)


def test_tyres_show_the_pace_of_the_stint_asked_and_stops_the_positions() -> None:
    one = result("stint_degradation", {"driver": "LEC", "stint": 2}, {"stints": [{"start_lap": 21, "end_lap": 53}]})
    every = result("stint_degradation", {"driver": "LEC"}, {"stints": [{"start_lap": 1, "end_lap": 20}, {}]})
    stops = result("pit_stop_loss", {"driver": "LEC"}, {"stops": []})

    assert chart_for(one) == FactChart(kind="pace", drivers=["LEC"], from_lap=21, to_lap=53)
    assert chart_for(every) == FactChart(kind="pace", drivers=["LEC"])
    assert chart_for(stops) == FactChart(kind="positions", drivers=["LEC"])


def test_a_failed_analysis_or_one_no_chart_shows_has_none() -> None:
    assert chart_for(result("pit_stop_loss", {"driver": "LEC"}, None, error="no stop")) is None
    assert chart_for(result("session_result", {"session": "R"}, {"results": []})) is None
