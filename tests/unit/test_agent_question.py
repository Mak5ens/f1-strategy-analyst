"""A question on a race chosen from its page (LAB-203), on the synthetic season of test_grand_prix: the race is taken
as given, never asked, and the plan offers what a question on a choice is answered against. No model is called."""

from typing import Any

import pytest
from test_grand_prix import write_lake

from core.agent import Analysis, Clarification, Point, Result
from f1.agent.theme import Draft, DraftPoint, F1Theme, Takeaway, TitledPoint
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


def test_a_debrief_is_drafted_as_a_summary_titled_moments_and_a_takeaway(
    theme: F1Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2})
    assert not isinstance(subject, Clarification)
    written = Draft(
        summary=DraftPoint(text="Verstappen gagne, parti 2e.", facts=["result"]),
        points=[
            TitledPoint(title="Norris s'arrête tard", text="Il rentre aux tours 20 et 40.", facts=["stops:NOR"]),
            TitledPoint(title="Le rythme de Norris", text="Il tient ses pneus.", facts=["stints:NOR"]),
            TitledPoint(title="L'undercut de Verstappen paie", text="Il rentre au tour 3.", facts=["stops:VER"]),
        ],
        takeaway=Takeaway(text="Le premier à s'arrêter a gagné."),
    )
    monkeypatch.setattr("f1.agent.theme.complete_json", lambda *args, **kwargs: written)

    points = theme.draft("Débrief", subject, [], [], {}, session_id=None)

    # The moments in the order of the race; one naming no lap stays after the one before it.
    assert [(point.id, point.kind, point.title, point.when) for point in points] == [
        ("S", "summary", None, None),
        ("P1", "point", "L'undercut de Verstappen paie", "Tour 3"),
        ("P2", "point", "Norris s'arrête tard", "Tours 20 à 40"),
        ("P3", "point", "Le rythme de Norris", None),
        ("T", "takeaway", None, None),
    ]
    published = theme.render(subject, points, [])
    assert "Verstappen gagne, parti 2e.\n\n## L'undercut de Verstappen paie\n\nIl rentre au tour 3." in published
    assert "## À retenir\n\nLe premier à s'arrêter a gagné." in published


def test_a_title_and_a_takeaway_hold_no_number(theme: F1Theme) -> None:
    titled = Point(id="P1", title="L'overcut coûte 5,4 s", text="Hamilton perd 5,4 s.", facts=["cycle:HAM:RUS"])
    takeaway = Point(id="T", kind="takeaway", text="Les 2 pilotes ont fini à leur place.")

    assert theme.check(titled) == ["a number in the title: keep the numbers in the text, which cites their analyses"]
    assert theme.check(takeaway) == ["a number in the takeaway: it says what the race means, without a number"]


def test_who_was_ahead_is_checked_without_a_model(theme: F1Theme) -> None:
    subject = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2})
    assert not isinstance(subject, Clarification)
    result = Result(id="result", tool="session_result", label="Classement", arguments={"season": 2025, "round": 2})
    result.output = theme.run(Analysis(id="result", tool="session_result", label="Classement",
                                       arguments={"season": 2025, "round": 2, "session": "R"}))  # fmt: skip

    found = theme.faithful(Point(id="S", text="Leclerc finit devant Verstappen."), [result], [], session_id=None)

    assert found == ["sens, contredit (code) : « Charles Leclerc devant Max Verstappen » ; les analyses mettent "
                     "Max Verstappen devant"]  # fmt: skip


def test_the_moments_of_a_race_are_planned_by_code(theme: F1Theme) -> None:
    subject = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2, "moments": True, "drivers": [],
                             "teams": []})  # fmt: skip
    assert not isinstance(subject, Clarification)

    plan = theme.candidates(subject)

    assert [analysis.id for analysis in plan] == ["result", "neutralizations", "penalties", "moments"]
    assert theme.choose("Les moments", subject, plan, session_id=None) == [analysis.id for analysis in plan]
    moments = theme.run(next(analysis for analysis in plan if analysis.id == "moments"))
    assert moments["moments"] == []  # nothing in this race moved the order
    assert moments["lecture"] == ["Aucun moment de la course n'a fait bouger le classement de façon mesurable."]


def test_a_prepared_team_debrief_is_resolved_from_what_code_gave(theme: F1Theme) -> None:
    subject = theme.resolve({**NOTHING_NAMED, "season": 2025, "round": 2, "prepared": "team", "teams": ["Ferrari"],
                             "drivers": ["LEC", "HAM"]})  # fmt: skip

    assert not isinstance(subject, Clarification)
    assert (subject["kind"], subject["focus"], subject["prepared"]) == ("team", ["LEC", "HAM"], "team")


def test_numbers_in_words_are_put_in_digits_before_the_checks() -> None:
    from f1.agent.theme import in_digits

    assert in_digits("Antonelli perd trois places, puis Une place ; vingt tours plus tard, deux dixièmes.") == (
        "Antonelli perd 3 places, puis 1 place ; 20 tours plus tard, 2 dixièmes."
    )
    assert in_digits("Il finit deuxième, un arrêt plus tard.") == "Il finit deuxième, un arrêt plus tard."


def test_what_a_question_asks_is_read_by_code_whatever_the_model_picks(
    theme: F1Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = theme.free_subject("Quels pneus a utilisés Leclerc ?", 2025, 2, ["Charles Leclerc"])
    assert not isinstance(subject, Clarification)
    plan = theme.candidates(subject)
    picked = type("Picked", (), {"analyses": ["tyres:LEC"], "rule_question": None})()
    monkeypatch.setattr("f1.agent.theme.complete_json", lambda *args, **kwargs: picked)

    assert theme.pick("Quels pneus a utilisés Leclerc ?", subject, plan, [], session_id=None).analyses == [
        "strategies",
        "tyres:LEC",
    ]
    assert theme.pick("Qui a signé la pole ?", subject, plan, [], session_id=None).analyses[0] == "qualifying"


def test_a_question_on_two_drivers_stops_gets_their_cycle_and_the_neutralizations(
    theme: F1Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    question = "Pourquoi Verstappen a-t-il perdu sa place face à Leclerc lors de leurs arrêts aux stands ?"
    subject = theme.free_subject(question, 2025, 2, ["Max Verstappen", "Charles Leclerc"])
    assert not isinstance(subject, Clarification)
    picked = type("Picked", (), {"analyses": ["gap:VER:LEC"], "rule_question": None})()
    monkeypatch.setattr("f1.agent.theme.complete_json", lambda *args, **kwargs: picked)

    analyses = theme.pick(question, subject, theme.candidates(subject), [], session_id=None).analyses

    assert analyses[:2] == ["cycle:VER:LEC", "neutralizations"]
