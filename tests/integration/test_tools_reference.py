"""The tools on reference races, against what public race reports say. The races are ingested from the real
sources into a temporary lake (the FastF1 cache makes it fast after the first run).

- 2024 Hungarian GP: McLaren stopped Norris first at the second stops; the undercut put him ahead of Piastri,
  who got the win back by team order and won by 2.141 s.
- 2024 São Paulo GP: a VSC, a safety car, then a red flag on lap 32 (Colapinto's crash), restarted with a
  rolling start, and a last safety car.
- 2025 Australian GP: three safety cars, on laps 1, 34 and 47.
- 2025 Italian GP: Norris's 5.9 s stop (Piastri's: 1.9 s) let Piastri out ahead; low tyre wear at Monza.
"""

from typing import Any

import pytest

from core.lake import Lake, LakeSettings
from f1.data import connect
from f1.data.ingest import Ingester, IngestSettings
from f1.data.sources import FastF1Source, JolpicaClient, OpenF1Client
from f1.tools import RaceData, catalog

pytestmark = pytest.mark.integration

ROUNDS = {2024: [13, 21], 2025: [1, 16]}


@pytest.fixture(scope="module")
def tools(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    lake = Lake(LakeSettings(uri=str(tmp_path_factory.mktemp("lake")), _env_file=None))
    settings = IngestSettings()
    with OpenF1Client() as openf1, JolpicaClient() as jolpica:
        ingester = Ingester(lake, FastF1Source(settings.fastf1_cache), openf1, jolpica, settings)
        for season, rounds in ROUNDS.items():
            outcomes = list(ingester.ingest_season(season, rounds=rounds))
            assert [outcome.status for outcome in outcomes] == ["ingested"] * len(rounds), outcomes
    return {tool.name: tool for tool in catalog(RaceData(connect(lake)))}


def run(tools: dict[str, Any], name: str, **arguments: Any) -> dict[str, Any]:
    result: dict[str, Any] = tools[name].run(arguments).model_dump()
    return result


def test_hungary_2024_norris_undercut(tools: dict[str, Any]) -> None:
    cycle = run(tools, "pit_cycle", season=2024, round=13, driver="NOR", rival="PIA", driver_stop=2)
    assert (cycle["driver_stop_lap"], cycle["rival_stop_lap"], cycle["first_to_stop"]) == (45, 47, cycle["driver"])
    assert cycle["driver_passed_rival"]
    assert cycle["gained_s"] > 3
    assert not cycle["neutralized"]


def test_hungary_2024_final_gap(tools: dict[str, Any]) -> None:
    gap = run(tools, "gap_between_drivers", season=2024, round=13, driver="NOR", reference_driver="PIA")
    assert gap["final_gap_s"] == pytest.approx(2.141, abs=0.001)


def test_sao_paulo_2024_neutralizations(tools: dict[str, Any]) -> None:
    result = run(tools, "neutralizations", season=2024, round=21)
    assert [(p["kind"], p["start_lap"], p["end_lap"]) for p in result["periods"]] == [
        ("virtual_safety_car", 28, 28),
        ("safety_car", 30, 32),
        ("red_flag", 32, 33),
        ("safety_car", 39, 42),
    ]
    assert 20 * 60 < result["periods"][2]["duration_s"] < 30 * 60


def test_australia_2025_three_safety_cars(tools: dict[str, Any]) -> None:
    result = run(tools, "neutralizations", season=2025, round=1)
    assert [p["start_lap"] for p in result["periods"]] == [1, 34, 47]
    assert result["safety_cars"] == 3


def test_monza_2025_slow_stop(tools: dict[str, Any]) -> None:
    (norris,) = run(tools, "pit_stop_loss", season=2025, round=16, driver="NOR")["stops"]
    (piastri,) = run(tools, "pit_stop_loss", season=2025, round=16, driver="PIA")["stops"]
    assert (norris["stationary_time_s"], piastri["stationary_time_s"]) == (5.9, 1.9)
    assert norris["time_lost_s"] - piastri["time_lost_s"] > 4
    assert 18 < piastri["time_lost_s"] < 28  # Monza's pit loss is about 23 s
    cycle = run(tools, "pit_cycle", season=2025, round=16, driver="PIA", rival="NOR")
    assert cycle["driver_passed_rival"]


def test_monza_2025_low_tyre_wear(tools: dict[str, Any]) -> None:
    stints = run(tools, "stint_degradation", season=2025, round=16, driver="VER")["stints"]
    assert [stint["compound"] for stint in stints] == ["MEDIUM", "HARD"]
    for stint in stints:
        assert stint["laps_used"] >= 10
        assert 0 < stint["degradation_s_per_lap"] < 0.15
        assert stint["degradation_s_per_lap"] > stint["raw_slope_s_per_lap"]  # the fuel burnt hid some wear
