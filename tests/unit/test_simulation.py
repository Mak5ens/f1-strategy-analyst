"""The strategy simulation (LAB-213) on a 30-lap race whose lines are exact, so that every projection is checked by
hand: AAA runs mediums (90 s + 0.1 s per lap of tyre age) to its stop on lap 15, then hards (89.5 s + 0.05 s), with
the fuel effect of the tools (0.06 s a lap); BBB runs 91 s laps and never stops."""

from typing import Any

import pytest

from core.tools import ToolError
from f1.tools.data import RaceData, SessionRef
from f1.tools.simulation import SimulationInput, simulate_strategy

FUEL = 0.06
STOP = 15


def lap_rows() -> list[dict[str, Any]]:
    rows = []
    for driver in ("AAA", "BBB"):
        end = 0.0
        for lap in range(1, 31):
            if driver == "AAA":
                first = lap <= STOP
                age = lap if first else lap - STOP
                time = (90 + 0.1 * age if first else 89.5 + 0.05 * age) - FUEL * (lap - 1)
                time += 10 if lap == STOP else 12 if lap == STOP + 1 else 0  # in-lap and out-lap
                stint, compound = (1, "MEDIUM") if first else (2, "HARD")
            else:
                age, time, stint, compound = lap, 91.0, 1, "HARD"
            end += time
            rows.append({"driver": driver, "lap_number": lap, "lap_time_s": round(time, 3),
                         "lap_end_session_s": round(end, 3), "stint": stint, "compound": compound, "tyre_life": age,
                         "pit_in_session_s": 1.0 if driver == "AAA" and lap == STOP else None,
                         "pit_out_session_s": 1.0 if driver == "AAA" and lap == STOP + 1 else None,
                         "track_status": "1", "deleted": False})  # fmt: skip
    return rows


class Race(RaceData):
    def __init__(self) -> None:
        self.rows = lap_rows()

    def laps(self, ref: SessionRef) -> list[dict[str, Any]]:
        return self.rows

    def pit_stops(self, ref: SessionRef, driver: str) -> list[dict[str, Any]]:
        if driver != "AAA":
            return []
        return [{"stop_number": 1, "lap": STOP, "pit_lane_time_s": 20.0, "stationary_time_s": 2.4,
                 "compound_before": "MEDIUM", "compound_after": "HARD", "red_flag": False}]  # fmt: skip


def simulate(stops: list[int]) -> Any:
    return simulate_strategy(Race(), SimulationInput(season=2025, round=1, driver="AAA", stops=stops, rival="BBB"))


def test_the_strategy_raced_projects_the_race_as_it_was() -> None:
    raced = simulate([STOP])
    assert raced.time_difference_s == 0
    assert all(lap.projected_gap_s == lap.raced_gap_s for lap in raced.laps)
    assert raced.model_error_s == 0  # exact lines


def test_a_later_stop_runs_the_mediums_two_laps_older_and_the_hards_two_laps_younger() -> None:
    later = simulate([17])
    # Laps 16 and 17 on mediums aged 16 and 17 instead of hards aged 1 and 2: 91.6 - 89.55, then 91.7 - 89.6.
    # Laps 18 to 30 on hards two laps younger: 0.05 x 2 gained on each of 13 laps. The stop's cost only moves.
    assert later.time_difference_s == pytest.approx(2.05 + 2.1 - 13 * 0.1, abs=1e-3)
    assert later.laps[-1].projected_gap_s == pytest.approx(later.laps[-1].raced_gap_s + 2.85, abs=1e-3)
    assert later.extended_laps == 2 and (later.stints[0].asked_from, later.stints[0].asked_to) == (1, 17)
    assert later.notes == ["stint 1: 2 laps beyond the tyre ages it was fitted on, its line extended"]


@pytest.mark.parametrize("stops", [[], [15, 20], [1], [30], [16, 14]])
def test_a_strategy_the_model_cannot_price_is_refused(stops: list[int]) -> None:
    with pytest.raises(ToolError):
        simulate(stops)


def test_the_validation_extends_a_stint_s_line_and_reads_its_error_back(tmp_path: Any) -> None:
    import json

    from f1.evals.simulation import expected_error, extension_errors

    steady = [row for row in lap_rows() if row["driver"] == "BBB"]  # 29 clean laps: 17 fitted, 12 projected
    errors = extension_errors(steady, 1)
    assert [k for k, _ in errors] == list(range(1, 13))
    assert all(abs(error) < 1e-6 for _, error in errors)  # an exact line projects exactly

    report = {"season": 2025, "buckets": [
        {"laps": [1, 5], "samples": 9, "median_s": 0.8, "p90_s": 3.0, "bias_s": -0.2},
        {"laps": [6, 10], "samples": 9, "median_s": 3.1, "p90_s": 8.3, "bias_s": -0.9},
    ]}  # fmt: skip
    (tmp_path / "simulation-2025.json").write_text(json.dumps(report))
    assert expected_error(0, 2025, tmp_path) is None  # no extension
    assert (found := expected_error(7, 2025, tmp_path)) and found["median_s"] == 3.1
    assert (longer := expected_error(14, 2025, tmp_path)) and longer["laps"] == [6, 10]  # the longest measured
