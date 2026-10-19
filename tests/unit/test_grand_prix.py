"""The page of a Grand Prix on the synthetic 10-lap race of test_tools, held as round 2 of 2025, after a round 1 that
only left standings, and before a round 3 whose weekend has started but whose race is not run yet."""

from collections.abc import Iterator
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_api import FakeRequests
from test_tools import MESSAGES, T0, race_laps, race_pit_stops

from core.lake import Lake, LakeSettings
from f1.api import app, get_grand_prix, get_requests
from f1.data import connect, schema, transform
from f1.grand_prix import GrandPrix

RACE: dict[str, int | str] = {"season": 2025, "round": 2, "session": "R"}


def stints() -> pd.DataFrame:
    rows = []
    for driver, stop in (("VER", 3), ("LEC", 5)):
        rows.append({"driver": driver, "stint": 1, "compound": "MEDIUM", "fresh_tyre": True, "start_lap": 1,
                     "end_lap": stop, "laps": stop})  # fmt: skip
        rows.append({"driver": driver, "stint": 2, "compound": "HARD", "fresh_tyre": False, "start_lap": stop + 1,
                     "end_lap": 10, "laps": 10 - stop})  # fmt: skip
    return pd.DataFrame(rows)


def results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"driver": "VER", "driver_number": "1", "driver_id": "max_verstappen", "full_name": "Max Verstappen",
             "team": "Red Bull Racing", "team_id": "red_bull", "position": 1, "classified_position": "1",
             "grid_position": 2, "status": "Finished", "points": 25, "laps": 10, "race_time_s": 921.0},
            {"driver": "LEC", "driver_number": "16", "driver_id": "leclerc", "full_name": "Charles Leclerc",
             "team": "Ferrari", "team_id": "ferrari", "position": 2, "classified_position": "2", "grid_position": 1,
             "status": "Finished", "points": 18, "laps": 10, "gap_to_winner_s": 1.5},
            {"driver": "HAM", "driver_number": "44", "driver_id": "hamilton", "full_name": "Lewis Hamilton",
             "team": "Ferrari", "team_id": "ferrari", "position": 3, "classified_position": "3", "grid_position": 0,
             "status": "Lapped", "points": 15, "laps": 9},
            {"driver": "NOR", "driver_number": "4", "driver_id": "norris", "full_name": "Lando Norris",
             "team": "McLaren", "team_id": "mclaren", "position": 4, "classified_position": "R", "grid_position": 3,
             "status": "Retired", "points": 0, "laps": 2},
        ]
    )  # fmt: skip


def driver_standings(round_number: int) -> pd.DataFrame:
    # After round 1: LEC, NOR, VER. Round 2 swaps VER and NOR.
    order = ["LEC", "NOR", "VER"] if round_number == 1 else ["LEC", "VER", "NOR"]
    ids = {"LEC": "leclerc", "NOR": "norris", "VER": "max_verstappen"}
    return pd.DataFrame(
        [
            {"position": position, "driver_id": ids[code], "driver": code, "points": 50 - 10 * position, "wins": 0}
            for position, code in enumerate(order, start=1)
        ]
    )


def constructor_standings(round_number: int) -> pd.DataFrame:
    order = ["mclaren", "ferrari", "red_bull"] if round_number == 1 else ["ferrari", "mclaren", "red_bull"]
    names = {"mclaren": "McLaren", "ferrari": "Ferrari", "red_bull": "Red Bull"}
    return pd.DataFrame(
        [
            {
                "position": position,
                "constructor_id": team,
                "constructor_name": names[team],
                "points": 80 - 20 * position,
                "wins": 1 if team == "red_bull" else 0,
            }
            for position, team in enumerate(order, start=1)
        ]
    )


def weather() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "session_time_s": 60.0 * minute,
                "air_temp_c": 20 + minute,
                "track_temp_c": 35 + 2 * minute,
                "humidity_pct": 50 + 10 * minute,
                "rainfall": minute == 2,
            }
            for minute in range(3)
        ]
    )


def write_lake(uri: str) -> Lake:
    """The synthetic season in a lake; the front's end-to-end tests serve it in the CI, which has no race data:

    uv run python -c "import sys; sys.path[:0] = ['tests/unit']; import test_grand_prix as t; t.write_lake('data/lake')"
    """
    lake = Lake(LakeSettings(uri=uri, _env_file=None))

    def write(name: str, frame: pd.DataFrame, table_schema: Any, **key: int | str) -> None:
        file = f"{key['round']:02d}-{key['session']}" if "session" in key else f"{key['round']:02d}"
        lake.write_parquet(f"{name}/2025/{file}.parquet", transform.to_table(frame, table_schema, **key))

    sessions = [
        (1, "R", "Australian Grand Prix", "Melbourne", "Australia", T0),
        (2, "S", "Chinese Grand Prix", "Shanghai", "China", T0 + pd.Timedelta(days=6)),
        (2, "R", "Chinese Grand Prix", "Shanghai", "China", T0 + pd.Timedelta(days=7)),
        (3, "FP1", "Japanese Grand Prix", "Suzuka", "Japan", T0 + pd.Timedelta(days=19)),
    ]
    for round_number, session, event, location, country, start in sessions:
        frame = pd.DataFrame([{"event_name": event, "location": location, "country": country, "start_utc": start,
                               "total_laps": 10 if session == "R" else None}])  # fmt: skip
        write("sessions", frame, schema.SESSIONS, season=2025, round=round_number, session=session)
    write("laps", race_laps(), schema.LAPS, **RACE)
    write("stints", stints(), schema.STINTS, **RACE)
    write("pit_stops", race_pit_stops(), schema.PIT_STOPS, **RACE)
    write("race_control_messages", pd.DataFrame(MESSAGES), schema.RACE_CONTROL_MESSAGES, **RACE)
    write("weather", weather(), schema.WEATHER, **RACE)
    write("results", results(), schema.RESULTS, **RACE)
    winner_round_1 = results().iloc[[1]].assign(position=1, classified_position="1")
    write("results", winner_round_1, schema.RESULTS, season=2025, round=1, session="R")
    for round_number in (1, 2):
        write("driver_standings", driver_standings(round_number), schema.DRIVER_STANDINGS, season=2025,
              round=round_number)  # fmt: skip
        write("constructor_standings", constructor_standings(round_number), schema.CONSTRUCTOR_STANDINGS,
              season=2025, round=round_number)  # fmt: skip
    return lake


@pytest.fixture(scope="module")
def lake(tmp_path_factory: pytest.TempPathFactory) -> Lake:
    return write_lake(str(tmp_path_factory.mktemp("lake")))


@pytest.fixture(scope="module")
def grand_prix(lake: Lake) -> GrandPrix:
    return GrandPrix(connect(lake))


def test_the_calendar_names_each_round_in_french_with_its_winner_once_raced(grand_prix: GrandPrix) -> None:
    calendar = grand_prix.calendar(2025)

    assert [(race.round, race.grand_prix, race.sprint) for race in calendar] == [
        (1, "Grand Prix d'Australie", False),
        (2, "Grand Prix de Chine", True),
        (3, "Grand Prix du Japon", False),
    ]
    assert [race.winner.code if race.winner else None for race in calendar] == ["LEC", "VER", None]
    assert calendar[1].winner and calendar[1].winner.colour == "#3671c6"
    assert calendar[1].date == T0 + pd.Timedelta(days=7) and calendar[2].date is None
    assert grand_prix.seasons() == [2025]


def test_the_featured_races_start_with_the_last_one_raced(grand_prix: GrandPrix) -> None:
    assert [race.round for race in grand_prix.featured([])] == [2, 1]
    assert [race.round for race in grand_prix.featured([(2025, 1), (2025, 3)], count=1)] == [2]


def test_the_classification_counts_the_places_gained_from_the_grid(grand_prix: GrandPrix) -> None:
    race = grand_prix.race(2025, 2)
    assert race is not None

    rows = [(row.position_text, row.driver.code, row.grid, row.places_gained, row.laps_behind)
            for row in race.classification]  # fmt: skip
    assert rows == [
        ("1", "VER", 2, 1, None),
        ("2", "LEC", 1, -1, None),
        ("3", "HAM", 0, 1, 1),  # from the pit lane: counted from the back of a 4-car grid
        ("R", "NOR", 3, None, None),
    ]
    assert race.classification[0].time_s == 921.0 and race.classification[1].gap_s == 1.5
    assert race.total_laps == 10


def test_best_laps_and_strategies_come_from_the_laps_and_the_tools(grand_prix: GrandPrix) -> None:
    race = grand_prix.race(2025, 2)
    assert race is not None

    assert race.fastest_lap and (race.fastest_lap.driver.code, race.fastest_lap.lap_time_s) == ("LEC", 89.5)
    assert [(lap.driver.code, lap.lap, lap.gap_s) for lap in race.best_laps] == [("LEC", 7, 0.0), ("VER", 2, 0.5)]
    strategies = {strategy.driver.code: strategy for strategy in race.strategies}
    assert list(strategies) == ["VER", "LEC"]  # finishing order, drivers without stints left out
    assert [(stint.compound, stint.start_lap, stint.end_lap) for stint in strategies["VER"].stints] == [
        ("MEDIUM", 1, 3),
        ("HARD", 4, 10),
    ]
    (stop,) = strategies["VER"].stops
    assert (stop.lap, stop.time_lost_s, stop.compound_after) == (3, 16.0, "HARD")  # as pit_stop_loss computes it


def test_neutralizations_penalties_standings_and_weather(grand_prix: GrandPrix) -> None:
    race = grand_prix.race(2025, 2)
    assert race is not None

    assert [period.kind for period in race.neutralizations] == [
        "safety_car",
        "virtual_safety_car",
        "safety_car",
        "red_flag",
        "safety_car",
    ]
    assert race.penalties == []
    assert [(row.driver.code, row.driver.name, row.change) for row in race.driver_standings] == [
        ("LEC", "Charles Leclerc", 0),
        ("VER", "Max Verstappen", 1),
        ("NOR", "Lando Norris", -1),
    ]
    teams = [(row.team, row.colour, row.change) for row in race.team_standings]
    assert teams[0] == ("Ferrari", "#e8002d", 1)
    assert teams[2] == ("Red Bull Racing", "#3671c6", 0)  # named as the results name it, to find its colour
    assert race.weather and (race.weather.air_temp_max_c, race.weather.track_temp_max_c) == (22, 39)
    assert race.weather.humidity_pct == 60 and race.weather.rainfall


def test_a_round_not_raced_yet_has_a_page_without_results(grand_prix: GrandPrix) -> None:
    race = grand_prix.race(2025, 3)

    assert race is not None and race.summary.winner is None
    assert race.classification == [] and race.strategies == [] and race.weather is None
    assert grand_prix.race(2025, 9) is None


def test_the_laps_of_a_race_give_the_gaps_the_gaps_tool_computes(grand_prix: GrandPrix, lake: Lake) -> None:
    from f1.tools.data import RaceData
    from f1.tools.gaps import GapInput, gap_between_drivers

    laps = grand_prix.laps(2025, 2)
    assert laps is not None and grand_prix.laps(2025, 3) is None  # not raced yet

    drivers = {row.driver.code: row for row in laps.drivers}
    assert list(drivers) == ["VER", "LEC", "HAM", "NOR"]  # finishing order, drivers without laps kept
    assert (drivers["VER"].grid, drivers["HAM"].grid, drivers["HAM"].laps) == (2, 0, [])
    ver, lec = ({lap.lap: lap for lap in drivers[code].laps} for code in ("VER", "LEC"))
    assert [ver[lap].position for lap in (3, 4, 6)] == [1, 2, 1]
    assert (ver[3].pit, ver[4].pit, ver[4].compound, ver[4].tyre_age) == ("in", "out", "HARD", 1)
    assert min(ver[lap].gap_s or 0 for lap in ver) == 0.0  # the leader's own gap

    tool = gap_between_drivers(RaceData(connect(lake)), GapInput(**RACE, driver="LEC", reference_driver="VER"))
    for row in tool.laps:  # the chart's gaps are the tool's: LEC's gap to the leader less VER's
        mine, theirs = lec[row.lap].gap_s, ver[row.lap].gap_s
        assert mine is not None and theirs is not None
        assert round(mine - theirs, 3) == row.gap_s


def test_the_laps_carry_each_stint_s_degradation_as_the_tool_computes_it(grand_prix: GrandPrix, lake: Lake) -> None:
    from f1.tools.data import RaceData
    from f1.tools.degradation import DegradationInput, stint_degradation

    laps = grand_prix.laps(2025, 2)
    assert laps is not None
    for row in laps.drivers[:2]:
        tool = stint_degradation(RaceData(connect(lake)), DegradationInput(**RACE, driver=row.driver.code))
        assert [
            (p.stint, p.start_lap, p.end_lap, p.degradation_s_per_lap, p.raw_slope_s_per_lap) for p in row.pace
        ] == [(s.stint, s.start_lap, s.end_lap, s.degradation_s_per_lap, s.raw_slope_s_per_lap) for s in tool.stints]
        assert all(len(p.laps) == s.laps_used for p, s in zip(row.pace, tool.stints, strict=True))


class FakeRules:
    def article(self, season: int, kind: str) -> dict[str, str] | None:
        return {"label": f"Article {kind} {season}", "url": "https://fia.example"} if kind == "safety_car" else None

    def decision(self, season: int, round_number: int, driver: str, kind: str, seconds: int | None) -> None:
        return None


def test_the_events_of_a_race_in_lap_order_with_their_links(lake: Lake) -> None:
    laps = GrandPrix(connect(lake), FakeRules()).laps(2025, 2)  # type: ignore[arg-type]
    assert laps is not None

    assert [event.kind for event in laps.events] == [period.kind for period in laps.neutralizations]
    assert [event.start_lap for event in laps.events] == sorted(event.start_lap for event in laps.events)
    links = {event.kind: event.link for event in laps.events}
    assert links["safety_car"] and links["safety_car"].label == "Article safety_car 2025"
    assert links["red_flag"] is None  # not found: no link


def test_a_duel_compares_two_drivers_round_by_round_by_code(grand_prix: GrandPrix) -> None:
    found = grand_prix.duel(2025, "VER", "LEC")
    assert found is not None and grand_prix.duel(2025, "VER", "XXX") is None

    first, second = found.rounds  # round 1 left only LEC's result: VER did not race it
    assert (first.round, first.race, first.pace) == (1, None, None)
    assert second.qualifying is None  # no qualifying in the synthetic season
    assert second.race and (second.race.first_position, second.race.second_position) == (1, 2)
    assert (second.race.first_points, second.race.second_points) == (25, 18)
    # Laps both covered clean: 2 and 7 to 10 (VER stops on 3, out on 4; LEC on 5, out on 6). VER less LEC:
    # -0.5, then 0.5 four times.
    assert second.pace and (second.pace.laps, second.pace.gap_s) == (5, 0.5)
    summary = found.summary
    assert (summary.race_first, summary.race_second, summary.points_first, summary.points_second) == (1, 0, 25, 18)
    assert (summary.qualifying_first, summary.qualifying_second, summary.qualifying_gap_s) == (0, 0, None)
    assert summary.pace_gap_s == 0.5


def test_the_drivers_of_a_season_most_points_first(grand_prix: GrandPrix) -> None:
    assert [driver.code for driver in grand_prix.drivers(2025)] == ["LEC", "VER", "HAM", "NOR"]
    assert grand_prix.drivers(2019) == []


@pytest.fixture
def client(grand_prix: GrandPrix) -> Iterator[TestClient]:
    requests = FakeRequests()
    app.dependency_overrides[get_grand_prix] = lambda: grand_prix
    app.dependency_overrides[get_requests] = lambda: requests
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_api_serves_the_calendar_and_the_race_pages(client: TestClient) -> None:
    assert client.get("/seasons").json() == [2025]
    assert [race["round"] for race in client.get("/races").json()] == [1, 2, 3]
    assert [race["round"] for race in client.get("/races/featured").json()] == [2, 1]

    race = client.get("/races/2025/2").json()

    assert race["summary"]["grand_prix"] == "Grand Prix de Chine"
    assert race["classification"][0]["driver"]["colour"] == "#3671c6"
    assert client.get("/races/2025/9").status_code == 404
    assert [row["driver"]["code"] for row in client.get("/races/2025/2/laps").json()["drivers"]][:2] == ["VER", "LEC"]
    assert client.get("/races/2025/3/laps").status_code == 404
    duel = client.get("/duels", params={"season": 2025, "drivers": ["ver", "lec"]}).json()
    assert (duel["first"]["code"], duel["summary"]["pace_gap_s"]) == ("VER", 0.5)
    assert client.get("/duels", params={"season": 2025, "drivers": ["VER"]}).status_code == 422
    assert client.get("/duels", params={"season": 2025, "drivers": ["VER", "XXX"]}).status_code == 404
    assert [driver["code"] for driver in client.get("/seasons/2025/drivers").json()][:2] == ["LEC", "VER"]
    refused = client.get("/races/2025/2/simulation", params={"driver": "ver"})
    assert refused.status_code == 422 and "tours propres" in refused.json()["detail"]  # 1 clean lap on mediums


def test_the_debriefs_of_a_race(client: TestClient) -> None:
    requests = app.dependency_overrides[get_requests]()
    for thread, round_number in (("a", 2), ("b", 1)):
        requests.rows[thread] = {"thread_id": thread, "request": "Débrief", "status": "published", "waiting": None,
                                 "subject": {"season": 2025, "round": round_number, "event": "Chinese Grand Prix"},
                                 "created_at": T0, "updated_at": T0}  # fmt: skip

    debriefs = client.get("/debriefs", params={"season": 2025, "round": 2}).json()

    assert [debrief["id"] for debrief in debriefs] == ["a"]
    assert [race["round"] for race in client.get("/races/featured").json()] == [2, 1]
