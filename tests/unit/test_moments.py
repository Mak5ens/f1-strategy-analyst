"""The moments that made a race (LAB-204), on a synthetic 6-lap race whose every score is computed by hand.

Grid: VER, NOR, LEC, HAM. HAM gains 2 places at the start (4th to 2nd: 18 - 12 points, plus 2 tenths: 6.2). NOR
passes HAM for 2nd on lap 3 (18 - 15 + 0.1: 3.1), then VER for the lead on lap 4 (25 - 18 + 0.1: 7.1). On lap 5,
VER drops from 2nd to 4th without stopping (6.2), passed by HAM and LEC, then retires.
"""

from typing import Any

import pandas as pd
import pytest

from core.lake import Lake, LakeSettings
from f1.agent.readings import order_problems, reading
from f1.data import connect, schema, transform
from f1.tools import RaceData
from f1.tools.moments import MomentsInput, Worth, key_moments, passes

KEY: dict[str, int | str] = {"season": 2025, "round": 1, "session": "R"}
ORDER = {  # positions at the end of each lap
    1: ["VER", "HAM", "NOR", "LEC"],
    2: ["VER", "HAM", "NOR", "LEC"],
    3: ["VER", "NOR", "HAM", "LEC"],
    4: ["NOR", "VER", "HAM", "LEC"],
    5: ["NOR", "HAM", "LEC", "VER"],
    6: ["NOR", "HAM", "LEC"],
}
NAMES = {"VER": "Max Verstappen", "NOR": "Lando Norris", "LEC": "Charles Leclerc", "HAM": "Lewis Hamilton"}


def laps() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"driver": driver, "lap_number": lap, "position": position, "lap_time_s": 90.0,
             "lap_end_session_s": 1000.0 + 90 * lap + position, "track_status": "1", "deleted": False}
            for lap, order in ORDER.items()
            for position, driver in enumerate(order, start=1)
        ]
    )  # fmt: skip


def results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"driver": "NOR", "position": 1, "classified_position": "1", "grid_position": 2, "status": "Finished"},
            {"driver": "HAM", "position": 2, "classified_position": "2", "grid_position": 4, "status": "Finished"},
            {"driver": "LEC", "position": 3, "classified_position": "3", "grid_position": 3, "status": "Finished"},
            {"driver": "VER", "position": 4, "classified_position": "R", "grid_position": 1, "status": "Engine"},
        ]
    )


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> RaceData:
    lake = Lake(LakeSettings(uri=str(tmp_path_factory.mktemp("lake")), _env_file=None))
    tables = {"laps": (laps(), schema.LAPS), "results": (results(), schema.RESULTS),
              "pit_stops": (pd.DataFrame(), schema.PIT_STOPS)}  # fmt: skip
    for name, (frame, table_schema) in tables.items():
        lake.write_parquet(f"{name}/2025/01-R.parquet", transform.to_table(frame, table_schema, **KEY))
    return RaceData(connect(lake))


def moments(data: RaceData) -> list[dict[str, Any]]:
    output = key_moments(data, MomentsInput(season=2025, round=1))
    return [moment.model_dump(exclude_defaults=True) for moment in output.moments]


def test_a_moment_is_worth_the_points_it_moved() -> None:
    worth = Worth("R")
    assert worth.between(2, 1) == 7.1  # a pass for the lead
    assert worth.between(15, 10) == 1.5  # from 15th to 10th: 1 point, 5 places
    assert Worth("S").between(2, 1) == 1.1  # a sprint's points


def test_passes_on_track_leave_out_the_start() -> None:
    by_driver: dict[str, dict[int, dict[str, Any]]] = {driver: {} for driver in NAMES}
    for lap, order in ORDER.items():
        for position, driver in enumerate(order, start=1):
            by_driver[driver][lap] = {"position": position, "track_status": "1", "pit_in_session_s": None,
                                      "pit_out_session_s": None}  # fmt: skip
    assert passes(by_driver) == [(3, "NOR", "HAM", 2), (4, "NOR", "VER", 1), (5, "HAM", "VER", 2),
                                 (5, "LEC", "VER", 3)]  # fmt: skip


def test_the_moments_are_ranked_by_points_two_of_a_kind_and_of_a_driver_at_most(data: RaceData) -> None:
    assert [(m["kind"], m["driver"], m["score"]) for m in moments(data)] == [
        ("overtakes", "NOR", 10.2),
        ("start", "HAM", 6.2),
        ("setback", "VER", 6.2),
        ("overtakes", "HAM", 3.1),  # LEC's pass, worth as much, is a third of a kind
        ("retirement", "VER", 2.1),
    ]
    first = moments(data)[0]
    assert (first["rank"], first["lap"], first["laps"], first["passed"]) == (1, 3, [3, 4], ["HAM", "VER"])


def test_the_moments_read_in_french_with_their_numbers(data: RaceData) -> None:
    output = key_moments(data, MomentsInput(season=2025, round=1)).model_dump(mode="json")
    sentences = reading("key_moments", output, NAMES)

    assert sentences[:3] == [
        "Moment 1 : Lando Norris réussit 2 dépassements en piste : Lewis Hamilton (tour 3), Max Verstappen (tour 4).",
        "Moment 2 : Lewis Hamilton gagne 2 places au départ, de 4e à 2e à la fin du tour 1.",
        "Moment 3 : Max Verstappen perd 2 places au tour 5, sans s'arrêter ni voiture de sécurité : de 2e à 4e. Les "
        "données ne disent pas pourquoi (sortie de piste, problème...).",
    ]
    assert sentences[4] == "Moment 5 : Max Verstappen abandonne au tour 5, alors 4e (Engine)."


def test_a_pit_cycle_moment_orders_the_two_drivers() -> None:
    cycle = {"kind": "pit_cycle", "driver": "NOR", "rival": "PIA", "rank": 1, "lap": 45, "places": 1}
    names = {"NOR": "Lando Norris", "PIA": "Oscar Piastri"}
    found = order_problems("Piastri reste devant Norris.", [{"moments": [cycle]}], names)
    assert len(found) == 1
