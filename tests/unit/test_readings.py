"""What the analyses mean, written by code (LAB-207): the readings the debrief rephrases, and the check of who was
ahead, on the numbers of Monza 2025 (Ferrari against Piastri and Russell)."""

from typing import Any

import pytest

from core.numbers import unverified_numbers
from f1.agent.readings import order_problems, reading

NAMES = {"LEC": "Charles Leclerc", "PIA": "Oscar Piastri", "HAM": "Lewis Hamilton", "RUS": "George Russell",
         "ALB": "Alexander Albon"}  # fmt: skip
UNDERCUT_SHORT: dict[str, Any] = {
    "driver": "LEC", "rival": "PIA", "driver_stop_lap": 33, "rival_stop_lap": 45, "gap_before_s": 7.194,
    "gap_after_s": 4.193, "gained_s": 3.001, "ahead_before": "PIA", "ahead_after": "PIA", "neutralized": False,
}  # fmt: skip
OVERCUT_LOST: dict[str, Any] = {
    "driver": "HAM", "rival": "RUS", "driver_stop_lap": 38, "rival_stop_lap": 27, "gap_before_s": 1.515,
    "gap_after_s": 6.879, "gained_s": -5.364, "ahead_before": "RUS", "ahead_after": "RUS", "neutralized": False,
}  # fmt: skip
RIVAL_FAILED: dict[str, Any] = {
    "driver": "HAM", "rival": "ALB", "driver_stop_lap": 38, "rival_stop_lap": 41, "gap_before_s": -10.942,
    "gap_after_s": -11.586, "gained_s": 0.644, "ahead_before": "HAM", "ahead_after": "HAM", "neutralized": False,
}  # fmt: skip
CLASSIFICATION = {
    "classification": [
        {"driver": "PIA", "name": "Oscar Piastri", "position": "3", "grid": 3},
        {"driver": "LEC", "name": "Charles Leclerc", "position": "4", "grid": 4},
        {"driver": "RUS", "name": "George Russell", "position": "5", "grid": 5},
        {"driver": "HAM", "name": "Lewis Hamilton", "position": "6", "grid": 10},
        {"driver": "ALB", "name": "Alexander Albon", "position": "R", "grid": 14, "status": "Retired"},
    ]
}


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            UNDERCUT_SHORT,
            "Oscar Piastri reste devant Charles Leclerc au cycle d'arrêts (Charles Leclerc rentre au tour 33, 12 tours "
            "avant Oscar Piastri, arrêté au tour 45) : l'undercut de Charles Leclerc lui a rapporté 3,0 s, pas assez "
            "pour passer : l'écart passe de 7,2 s à 4,2 s.",
        ),
        (
            OVERCUT_LOST,
            "George Russell reste devant Lewis Hamilton au cycle d'arrêts (George Russell rentre au tour 27, 11 tours "
            "avant Lewis Hamilton, arrêté au tour 38) : l'overcut de Lewis Hamilton lui a coûté 5,4 s : l'écart passe "
            "de 1,5 s à 6,9 s.",
        ),
        (
            RIVAL_FAILED,  # told from the car behind, which is the rival here
            "Lewis Hamilton reste devant Alexander Albon au cycle d'arrêts (Lewis Hamilton rentre au tour 38, 3 tours "
            "avant Alexander Albon, arrêté au tour 41) : l'overcut d'Alexander Albon lui a coûté 0,6 s : l'écart "
            "passe de 10,9 s à 11,6 s.",
        ),
    ],
)
def test_a_pit_cycle_is_read_from_the_car_behind(output: dict[str, Any], expected: str) -> None:
    assert reading("pit_cycle", output, NAMES) == [expected]


def test_a_cycle_that_swaps_the_order_says_who_passed() -> None:
    swapped = {**UNDERCUT_SHORT, "ahead_after": "LEC", "gap_after_s": -1.2, "gained_s": 8.4}

    assert reading("pit_cycle", swapped, NAMES)[0].startswith(
        "Charles Leclerc passe devant Oscar Piastri grâce au cycle d'arrêts"
    )
    assert (
        "son undercut a réussi. Il était à 7,2 s derrière avant les arrêts, il est 1,2 s devant après."
        in (reading("pit_cycle", swapped, NAMES)[0])
    )


def test_a_reading_rounds_the_numbers_of_its_output_and_counts_only_laps() -> None:
    for output in (UNDERCUT_SHORT, OVERCUT_LOST, RIVAL_FAILED):
        apart = abs(output["driver_stop_lap"] - output["rival_stop_lap"])
        assert unverified_numbers(reading("pit_cycle", output, NAMES)[0], output) == [str(apart)]


def test_the_classification_tells_the_places_gained_from_the_grid() -> None:
    assert reading("session_result", CLASSIFICATION, NAMES) == [
        "Oscar Piastri : parti 3e, arrivé 3e, même place.",
        "Charles Leclerc : parti 4e, arrivé 4e, même place.",
        "George Russell : parti 5e, arrivé 5e, même place.",
        "Lewis Hamilton : parti 10e, arrivé 6e, 4 places gagnées.",
        "Alexander Albon : parti 14e, non classé (Retired).",
    ]


def test_a_degradation_measured_too_loosely_is_not_read() -> None:
    output = {"driver": "LEC", "stints": [
        {"stint": 1, "compound": "MEDIUM", "start_lap": 1, "end_lap": 33, "degradation_s_per_lap": -0.0054,
         "r_squared": 0.049},
        {"stint": 2, "compound": "HARD", "start_lap": 34, "end_lap": 53, "degradation_s_per_lap": 0.0612,
         "r_squared": 0.71},
    ]}  # fmt: skip

    assert reading("stint_degradation", output, NAMES) == [
        "Charles Leclerc, relais 1 en mediums, tours 1 à 33 : usure non mesurable, les temps au tour varient trop "
        "pour la lire.",
        "Charles Leclerc, relais 2 en durs, tours 34 à 53 : 0,06 s perdues par tour d'usure des pneus.",
    ]


def test_stops_and_neutralizations_read_as_sentences() -> None:
    stop = {"lap": 33, "time_lost_s": 24.824, "compound_before": "MEDIUM", "compound_after": "HARD",
            "neutralized": False, "red_flag": False}  # fmt: skip
    stops = {"driver": "LEC", "stops": [stop]}
    calm: dict[str, Any] = {"periods": []}

    assert reading("pit_stop_loss", stops, NAMES) == [
        "Charles Leclerc s'arrête au tour 33, 24,8 s perdues, des mediums aux durs."
    ]
    assert reading("neutralizations", calm, NAMES) == [
        "Aucune voiture de sécurité, voiture de sécurité virtuelle ni drapeau rouge pendant la course."
    ]
    assert reading("weather", {}, NAMES) == []


@pytest.mark.parametrize(
    ("text", "contradicted"),
    [
        ("Leclerc reste devant Piastri et Hamilton après leurs cycles d'arrêts, mais ne revient pas.", ["Piastri"]),
        ("Leclerc finit derrière Russell.", ["Russell"]),
        ("Piastri reste devant Leclerc.", []),
        ("Leclerc ne passe pas Piastri.", []),  # a negation is not read
        ("Russell ressort derrière Leclerc, qui finit devant lui.", []),
        ("Hamilton reste devant Albon.", []),  # nothing orders them: not contradicted
    ],
)
def test_who_was_ahead_is_checked_by_code(text: str, contradicted: list[str]) -> None:
    found = order_problems(text, [UNDERCUT_SHORT, OVERCUT_LOST, CLASSIFICATION], NAMES)

    assert len(found) == len(contradicted)
    assert all(name in problem for name, problem in zip(contradicted, found, strict=True))
