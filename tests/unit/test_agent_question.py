"""A question on a race chosen from its page (LAB-203), on the synthetic season of test_grand_prix: the race is taken
as given, never asked, and the plan offers what a question on a choice is answered against. No model is called."""

from typing import Any

import pytest
from test_grand_prix import write_lake

from core.agent import Clarification, Point
from f1.agent.theme import F1Theme
from f1.data import connect
from f1.tools import RaceData

NOTHING_NAMED: dict[str, Any] = {"seasons": [], "grands_prix": [], "mentions": {"drivers": [], "teams": []}}


@pytest.fixture(scope="module")
def theme(tmp_path_factory: pytest.TempPathFactory) -> F1Theme:
    lake = write_lake(str(tmp_path_factory.mktemp("lake")))
    return F1Theme(RaceData(connect(lake)), llm=None)  # type: ignore[arg-type]


def test_a_chosen_race_is_resolved_without_a_question(theme: F1Theme) -> None:
    subject = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2, "question": True})

    assert not isinstance(subject, Clarification)
    assert (subject["event"], subject["kind"]) == ("Chinese Grand Prix", "race")
    assert [driver["code"] for driver in subject["entry"]] == ["VER", "LEC", "HAM", "NOR"]
    assert subject["focus"] == ["VER", "LEC", "HAM"]


def test_a_round_the_data_does_not_have_is_asked_for(theme: F1Theme) -> None:
    asked = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 9})

    assert isinstance(asked, Clarification) and asked.field == "grand_prix"


def test_a_question_plans_the_others_choices_and_the_weather(theme: F1Theme) -> None:
    subject = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2, "question": True})
    assert not isinstance(subject, Clarification)
    debrief = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2})
    assert not isinstance(debrief, Clarification)

    plan = {analysis.id: analysis for analysis in theme.candidates(subject)}

    assert {"strategies", "weather"} <= set(plan)
    assert "strategies" not in {analysis.id for analysis in theme.candidates(debrief)}
    strategies = theme.run(plan["strategies"])
    assert strategies["start_compounds"] == {"MEDIUM": 2}
    assert [(d["driver"], d["grid"], d["stop_laps"]) for d in strategies["drivers"]] == [
        ("LEC", 1, [5]),
        ("VER", 2, [3]),
    ]
    weather = theme.run(plan["weather"])
    assert (weather["air_temp_start_c"], weather["rainfall"], weather["rain_minutes"]) == (20.0, True, 1)


def test_the_answer_is_titled_as_one(theme: F1Theme) -> None:
    subject = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2, "question": True})
    assert not isinstance(subject, Clarification)

    assert theme.render(subject, [], []).startswith("# Réponse : Grand Prix de Chine 2025")


def test_a_question_on_a_debrief_stays_on_its_race(theme: F1Theme) -> None:
    subject = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2})
    assert not isinstance(subject, Clarification)

    assert theme.scope(subject, "Détaille le cycle d'arrêts de Leclerc") is None
    assert theme.scope(subject, "Et à Shanghai, sous la voiture de sécurité ?") is None  # the same race, by its place
    assert theme.scope(subject, "Pourquoi pas comme en 2025 ?") is None
    refused = theme.scope(subject, "Et au GP de Monaco ?")
    assert refused is not None and refused.startswith("Cette question porte sur le Grand Prix de Monaco, pas sur le")
    assert "page de cette course" in refused and "question libre" in refused
    assert (theme.scope(subject, "Et en 2024 ?") or "").startswith("Cette question porte sur la saison 2024")


def test_an_article_named_needs_its_source(theme: F1Theme) -> None:
    named = Point(id="A1", text="Les pneus sont ceux de l'article B6.2.4.")

    assert theme.check(named) == ["names articles without citing their source: B6.2.4"]
    assert theme.check(named.model_copy(update={"sources": ["Q:S1"]})) == []
    assert theme.check(Point(id="A2", text="Leclerc a perdu 24.8 s au tour 33.")) == []
