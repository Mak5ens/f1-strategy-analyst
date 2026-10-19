"""The season view (LAB-215) on two rounds checked by hand: AAA and BBB drive for Alpha, CCC for Beta; round 2 has
a sprint. AAA wins round 1 and retires in round 2, which BBB wins."""

from typing import Any

import pytest

from f1.season import overview, race_gaps, standings
from f1.tools.data import RaceData


def result(round_: int, session: str, code: str, place: str, points: float, **times: float) -> dict[str, Any]:
    team = "Beta" if code == "CCC" else "Alpha"
    return {"round": round_, "session": session, "driver": code, "full_name": f"Driver {code}", "team": team,
            "classified_position": place, "position": int(place) if place.isdigit() else 20, "points": points,
            "grid_position": 1, **times}  # fmt: skip


RESULTS = [
    result(1, "Q", "AAA", "1", 0, q1_s=80.0, q3_s=79.0),
    result(1, "Q", "BBB", "2", 0, q1_s=80.5),
    result(1, "Q", "CCC", "3", 0, q1_s=80.79),
    result(1, "R", "AAA", "1", 25),
    result(1, "R", "BBB", "3", 15),
    result(1, "R", "CCC", "2", 18),
    result(2, "S", "AAA", "2", 7),
    result(2, "S", "BBB", "1", 8),
    result(2, "R", "BBB", "1", 25),
    result(2, "R", "AAA", "R", 0),  # retired
    result(2, "R", "CCC", "2", 18),
]


def laps(round_: int = 1) -> list[dict[str, Any]]:
    rows = []
    for lap in range(2, 14):  # 12 clean laps: Alpha's two cars at 90 and 91 s, Beta at 91.8 s
        for code, time in (("AAA", 90.0), ("BBB", 91.0), ("CCC", 91.8)):
            rows.append({"round": round_, "driver": code, "lap_number": lap, "lap_time_s": time, "track_status": "1",
                         "pit_in_session_s": None, "pit_out_session_s": None, "deleted": False})  # fmt: skip
    return rows


class Season(RaceData):
    def __init__(self) -> None:
        pass

    def season_results(self, season: int, sessions: Any) -> list[dict[str, Any]]:
        return [row for row in RESULTS if row["session"] in sessions]

    def season_laps(self, season: int, drivers: Any, session: str = "R") -> list[dict[str, Any]]:
        return laps(1)

    def events(self, season: int) -> list[dict[str, Any]]:
        return [{"round": 1, "event_name": "Italian Grand Prix"}, {"round": 2, "event_name": "Chinese Grand Prix"}]


def test_the_championship_adds_races_and_sprints_round_by_round() -> None:
    season = overview(Season(), 2025)
    assert season is not None
    assert [(r.round, r.grand_prix, r.sprint) for r in season.rounds] == [
        (1, "Grand Prix d'Italie", False),
        (2, "Grand Prix de Chine", True),
    ]
    drivers = {d.driver.code: d for d in season.drivers}
    assert drivers["AAA"].cumulative == [25, 32] and drivers["BBB"].cumulative == [15, 48]
    assert drivers["CCC"].cumulative == [18, 36] and drivers["CCC"].positions == [2, 2]
    assert [d.driver.code for d in season.drivers] == ["BBB", "CCC", "AAA"]
    retired = drivers["AAA"].results[1]
    assert retired is not None and (retired.text, retired.position, retired.points) == ("R", None, 7)
    assert drivers["BBB"].form_points == 48 and drivers["BBB"].wins == 1
    teams = {t.team: t for t in season.teams}
    assert teams["Alpha"].cumulative == [40, 80] and teams["Alpha"].wins == 2 and teams["Alpha"].position == 1


def test_a_tie_on_points_goes_to_the_count_back_of_race_places() -> None:
    # Both on 25 points: one win against a second and a third place.
    scored = {"X": {1: (25.0, (1,))}, "Y": {1: (10.0, (2,)), 2: (15.0, (3,))}}
    order, cumulative, positions = standings(scored, [1, 2])
    assert order == ["X", "Y"] and cumulative["Y"] == [10, 25] and positions["Y"] == [2, 2]


def test_the_teams_pace_in_qualifying_and_in_the_race() -> None:
    season = overview(Season(), 2025)
    assert season is not None
    teams = {t.team: t for t in season.teams}
    # Qualifying: Alpha's best 79.0 s, Beta's 80.79 s: 1.79 s, 2.266 % of the pole.
    assert teams["Alpha"].qualifying_gap_pct[0] == 0 and teams["Beta"].qualifying_gap_pct[0] == pytest.approx(2.266)
    # Race: Alpha's median of 90 and 91 s is 90.5 s, Beta's 91.8 s: 1.3 s, 1.436 % on every lap.
    assert teams["Beta"].race_gap_pct[0] == pytest.approx(1.436, abs=1e-3)
    assert teams["Alpha"].race_gap_pct == [0, None]  # round 2 has no laps here


def test_too_few_laps_give_no_race_pace() -> None:
    short = [lap for lap in laps() if lap["lap_number"] < 6]
    teams = {(1, "AAA"): "Alpha", (1, "BBB"): "Alpha", (1, "CCC"): "Beta"}
    assert race_gaps(short, teams, 1) == {}
