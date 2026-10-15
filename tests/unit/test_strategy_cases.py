"""The rule behind the strategy cases (LAB-201): penalties served at a stop, neutralizations by name, stops paired by
rank, and the cause of a swap, undercut and overcut never mixed up."""

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from f1.evals.strategy import (
    Duel,
    Penalty,
    RaceFacts,
    StopFacts,
    _paired,
    cause,
    elide,
    list_fr,
    neutralization,
    penalties,
    reason_fr,
    served_at,
)
from f1.tools.pit_cycle import PitCycleOutput
from f1.tools.pit_loss import StopLoss


def message(lap: int, text: str) -> dict[str, Any]:
    return {"lap": lap, "message": text, "time_utc": datetime(2025, 1, 1, tzinfo=UTC)}


def raw_stop(driver: str, number: int, lap: int, *, red_flag: bool = False) -> dict[str, Any]:
    return {"driver": driver, "stop_number": number, "lap": lap, "red_flag": red_flag}


def test_penalties_are_read_from_the_stewards_messages() -> None:
    given, served = penalties(
        [
            message(5, "FIA STEWARDS: 10 SECOND TIME PENALTY FOR CAR 1 (VER) - CAUSING A COLLISION"),
            message(9, "FIA STEWARDS: DRIVE THROUGH PENALTY FOR CAR 55 (SAI) - SPEEDING IN THE PIT LANE"),
            message(12, "FIA STEWARDS: 10 SECOND STOP/GO PENALTY FOR CAR 30 (LAW) - RELEASING IN UNSAFE CONDITION"),
            message(23, "FIA STEWARDS: PENALTY SERVED - 10 SECOND TIME PENALTY FOR CAR 1 (VER)"),
            message(30, "FIA STEWARDS: INCIDENT INVOLVING CAR 22 (TSU) UNDER INVESTIGATION - FAILING TO SERVE TIME"),
            message(31, "DRS ENABLED"),
        ]
    )
    assert [(p.driver, p.kind, p.seconds, p.lap) for p in given] == [
        ("VER", "time", 10, 5),
        ("SAI", "drive_through", None, 9),
        ("LAW", "stop_go", 10, 12),
    ]
    assert served == [("VER", 23)]


def test_a_time_penalty_is_served_at_the_next_stop() -> None:
    stops = [raw_stop("VER", 1, 3), raw_stop("VER", 2, 29), raw_stop("VER", 3, 40)]
    penalty = Penalty("VER", "time", 10, "CAUSING A COLLISION", 5)
    # Before 2025, no "PENALTY SERVED": the first stop on or after the lap it was given.
    assert served_at(stops, [penalty], []) == {("VER", 2): [penalty]}
    # Since 2025, the last stop before the message.
    assert served_at(stops, [penalty], [("VER", 41)]) == {("VER", 3): [penalty]}
    # A red flag tyre change serves nothing.
    assert served_at([raw_stop("VER", 1, 29, red_flag=True), *stops[2:]], [penalty], []) == {("VER", 3): [penalty]}


def test_reasons_and_names_read_in_french() -> None:
    assert reason_fr("CAUSING A COLLISION (15:04:29)") == "pour avoir provoqué une collision"
    assert reason_fr("SOMETHING NEW") == "(« something new »)"
    assert Penalty("HAM", "time", 10, "LEAVING THE TRACK AND GAINING AN ADVANTAGE", 16).french() == (
        "une pénalité de 10 s pour avoir gagné un avantage en sortant de la piste"
    )
    assert (elide("de", "Oscar Piastri"), elide("que", "Max Verstappen")) == ("d'Oscar Piastri", "que Max Verstappen")
    assert list_fr([18, 19, 20]) == "18, 19 et 20"


@pytest.mark.parametrize(
    ("statuses", "named"),
    [
        (["1", "14"], "voiture de sécurité"),
        (["167"], "voiture de sécurité virtuelle (VSC)"),
        (["45"], "drapeau rouge"),
        (["12", "1"], None),  # a yellow flag does not neutralize the race
    ],
)
def test_a_neutralization_is_named(statuses: list[str], named: str | None) -> None:
    assert neutralization(statuses) == named


def stop(driver: str, lap: int, *, rank: int = 1, stationary: float = 2.5, **values: Any) -> StopFacts:
    loss = StopLoss(
        stop_number=rank, lap=lap, pit_lane_time_s=20.0, stationary_time_s=stationary, in_and_out_laps_s=None,
        reference_lap_s=None, reference_laps=0, time_lost_s=21.0, compound_before="MEDIUM", compound_after="HARD",
        neutralized=False, red_flag=False,
    )  # fmt: skip
    return StopFacts(driver=driver, number=rank, lap=lap, loss=loss, tyre_age=lap, fresh_after=True, pit_in_s=None,
                     neutralized_by=values.pop("neutralized_by", None), **values)  # fmt: skip


def test_stops_pair_by_rank_and_closeness() -> None:
    # Canada 2025: Leclerc's 1st stop (lap 28) was compared with Russell's 2nd (lap 42). Only stops of the same rank
    # are compared now; 1st against 1st are 16 laps apart, not one cycle.
    lec = [stop("LEC", 28), stop("LEC", 50, rank=2)]
    rus = [stop("RUS", 12), stop("RUS", 42, rank=2)]
    assert not _paired(lec[0], rus[0], lec, rus)
    assert _paired(lec[1], rus[1], lec, rus)
    # Same rank, but the rival's stop is closer to another one of mine: not the same cycle.
    mine, theirs = [stop("NOR", 20), stop("NOR", 30, rank=2)], [stop("PIA", 29), stop("PIA", 45, rank=2)]
    assert not _paired(mine[0], theirs[0], mine, theirs)


class FakeRace:
    """What `cause` reads of a race: names, and laps (none here, so no pace to compare)."""

    def __init__(self) -> None:
        self.names = {"NOR": "Lando Norris", "PIA": "Oscar Piastri"}
        self.laps: dict[str, dict[int, Any]] = {"NOR": {}, "PIA": {}}

    def name(self, code: str) -> str:
        return self.names[code]


def race() -> RaceFacts:
    return cast(RaceFacts, FakeRace())


def duel(nor: StopFacts, pia: StopFacts, *, before: float, after: float) -> Duel:
    """NOR against PIA; a gap is NOR's time minus PIA's: positive, NOR behind."""
    cycle = PitCycleOutput(
        season=2025, round=1, session="R", driver="NOR", rival="PIA", driver_stop_lap=nor.lap,
        rival_stop_lap=pia.lap, kind="undercut" if nor.lap < pia.lap else "overcut", lap_before=19, lap_after=26,
        gap_before_s=before, gap_after_s=after, gained_s=round(before - after, 3), position_before=2,
        rival_position_before=1, position_after=1, rival_position_after=2, driver_passed_rival=before > 0 > after,
        rival_passed_driver=before < 0 < after, neutralized=False,
    )  # fmt: skip
    return Duel("NOR", "PIA", 1, cycle, {"NOR": nor, "PIA": pia})


def test_the_winner_stopping_first_is_an_undercut_and_later_an_overcut() -> None:
    undercut = cause(race(), duel(stop("NOR", 20), stop("PIA", 24), before=1.2, after=-1.5))
    assert undercut and undercut[0] == "undercut" and "Lando Norris s'est arrêté le premier" in undercut[1]
    overcut = cause(race(), duel(stop("NOR", 25), stop("PIA", 20), before=1.2, after=-1.5))
    assert overcut and overcut[0] == "overcut" and "resté en piste 5 tours de plus qu'Oscar Piastri" in overcut[1]


def test_a_penalty_served_at_the_stop_is_not_a_slow_stop() -> None:
    penalty = Penalty("PIA", "time", 5, "TRACK LIMITS", 10)
    found = cause(
        race(),
        duel(stop("NOR", 22), stop("PIA", 22, stationary=7.6, penalties=[penalty]), before=1.2, after=-2.0),
    )
    assert found and found[0] == "penalty" and "pénalité de 5 s" in found[1]
    # Only the penalty decides when the winner came out ahead by less than it.
    beyond = cause(
        race(),
        duel(stop("NOR", 20), stop("PIA", 24, stationary=7.6, penalties=[penalty]), before=1.2, after=-6.0),
    )
    assert beyond and beyond[0] == "undercut"


def test_a_stop_under_a_safety_car_is_named() -> None:
    found = cause(
        race(),
        duel(stop("NOR", 25, neutralized_by="voiture de sécurité"), stop("PIA", 20), before=1.2, after=-8.0),
    )
    assert found and found[0] == "neutralization" and "sous voiture de sécurité" in found[1]
    # The loser had the cheap stop and still lost: the rule cannot say why.
    assert (
        cause(
            race(), duel(stop("NOR", 25), stop("PIA", 20, neutralized_by="voiture de sécurité"), before=1.2, after=-1.0)
        )
        is None
    )
