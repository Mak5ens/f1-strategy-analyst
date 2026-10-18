"""The free question's paths (LAB-206) on the synthetic season of test_grand_prix: the rules from a scripted pipeline,
the data from the real F1 theme with its model steps scripted, so that the numbers are checked for real."""

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from test_grand_prix import write_lake

from core.agent import Analysis, Point, Result, Rule
from core.agent.chat import Chat, ChatLimits, Exchange, Pick
from core.retrieval.pipeline import Answer, Claim, Passage, Scope, Source
from core.tracing import Tracer
from f1.agent.theme import F1Theme
from f1.data import connect
from f1.grand_prix import GrandPrix
from f1.questions import FreeQuestions
from f1.router import Router
from f1.tools import RaceData


class ScriptedTheme(F1Theme):
    """The F1 theme, its catalog, tools and checks as they are; the model's pick and reply written in advance."""

    def __init__(self, data: RaceData, picked: Sequence[str], text: str) -> None:
        super().__init__(data, llm=None)  # type: ignore[arg-type]
        self.picked, self.text = list(picked), text
        self.subjects: list[Mapping[str, Any]] = []
        self.offered: list[str] = []

    def pick(self, question: str, subject: Mapping[str, Any], candidates: Sequence[Analysis],
             history: Sequence[Exchange], *, session_id: str | None) -> Pick:  # fmt: skip
        self.subjects.append(subject)
        self.offered = [analysis.id for analysis in candidates]
        return Pick(analyses=self.picked)

    def reply(self, question: str, subject: Mapping[str, Any], results: Sequence[Result], rules: Sequence[Rule],
              history: Sequence[Exchange], problems: Mapping[str, Sequence[str]], *,
              session_id: str | None) -> list[Point]:  # fmt: skip
        return [Point(id="A1", text=self.text, facts=[result.id for result in results])]


class ScriptedRules:
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.asked: list[str] = []

    def answer(self, question: str) -> Answer:
        self.asked.append(question)
        scope = Scope(
            {"season": [2026]}, notes=["La question ne précise pas de saison : réponse selon le règlement 2026."]
        )
        if not self.found:
            return Answer(question, claims=[], sources=[], scope=scope, abstention="below_threshold")
        passage = Passage(id="p1", payload={"url": "https://www.fia.com/regulation", "text": "…"}, rank=1)
        source = Source(id="S1", label="Règlement sportif F1 2026, article B5.13", text="Tyres may be changed.",
                        parent_id="B5.13", passages=[passage])  # fmt: skip
        claim = Claim(text="Les pneus peuvent être changés pendant la suspension (article B5.13).", sources=["S1"])
        return Answer(question, claims=[claim], sources=[source], scope=scope)


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> RaceData:
    return RaceData(connect(write_lake(str(tmp_path_factory.mktemp("lake")))))


def questions(data: RaceData, theme: F1Theme | None = None, rules: ScriptedRules | None = None) -> FreeQuestions:
    grand_prix = GrandPrix(data._db)
    chat = Chat(theme or ScriptedTheme(data, [], ""), tracer=Tracer(None), limits=ChatLimits(_env_file=None))
    return FreeQuestions(
        Router(*grand_prix.people()), grand_prix, rules=lambda: rules or ScriptedRules(), chat=lambda: chat
    )


def test_a_rule_question_is_answered_by_the_pipeline_with_its_sources(data: RaceData) -> None:
    rules = ScriptedRules()

    answer = questions(data, rules=rules).ask("Peut-on changer de pneus sous drapeau rouge ?")

    assert (answer.route, answer.status, rules.asked) == (
        "rules",
        "answered",
        ["Peut-on changer de pneus sous drapeau rouge ?"],
    )
    assert answer.points[0].sources == ["S1"] and answer.sources[0].url == "https://www.fia.com/regulation"
    assert answer.notes == ["La question ne précise pas de saison : réponse selon le règlement 2026."]
    assert answer.race is None


def test_a_rule_question_with_nothing_found_abstains(data: RaceData) -> None:
    answer = questions(data, rules=ScriptedRules(found=False)).ask("Quelle est la règle des drapeaux bleus ?")

    assert (answer.status, answer.points) == ("abstained", []) and "pas trouvé" in (answer.reason or "")


def test_a_question_on_the_data_of_a_race_is_answered_with_its_numbers_checked(data: RaceData) -> None:
    theme = ScriptedTheme(data, ["result"], "Verstappen a gagné en partant 2e.")

    answer = questions(data, theme).ask("Qui a gagné le GP de Chine 2025, et parti de quelle position ?")

    assert (answer.route, answer.status) == ("data", "answered")
    assert answer.race is not None and (answer.race.round, answer.race.grand_prix) == (2, "Grand Prix de Chine")
    assert [(fact.id, fact.label) for fact in answer.facts] == [("result", "Classement de la course")]
    assert theme.subjects[0]["free"] is True and theme.subjects[0]["focus"] == ["VER", "LEC", "HAM"]


def test_a_number_no_analysis_backs_is_withheld(data: RaceData) -> None:
    theme = ScriptedTheme(data, ["result"], "Verstappen a gagné avec 12.7 s d'avance.")

    answer = questions(data, theme).ask("Qui a gagné le GP de Chine 2025 ?")

    assert (answer.status, answer.points) == ("withheld", []) and "12.7" in (answer.reason or "")


def test_the_drivers_named_and_their_laps_choose_the_catalog(data: RaceData) -> None:
    theme = ScriptedTheme(data, [], "Les analyses ne le disent pas.")

    questions(data, theme).ask("Quel écart entre Leclerc et Verstappen au tour 4 du GP de Chine 2025 ?")

    subject = theme.subjects[0]
    assert (subject["named"], subject["focus"], subject["laps"]) == (["VER", "LEC"], ["VER", "LEC"], [4])
    assert "gap:VER:LEC" in theme.offered and "cycle:VER:LEC" in theme.offered
    gap = next(a for a in theme.candidates(subject) if a.id == "gap:VER:LEC")
    assert (gap.arguments["from_lap"], gap.arguments["to_lap"], gap.label) == (
        4,
        4,
        "Écart entre Max Verstappen et Charles Leclerc, tour 4",
    )


def test_a_second_stop_named_is_the_cycle_offered(data: RaceData) -> None:
    theme = ScriptedTheme(data, [], "Les analyses ne le disent pas.")

    questions(data, theme).ask(
        "Pourquoi Leclerc est-il ressorti derrière Verstappen après leurs 2es arrêts en Chine 2025 ?"
    )

    cycle = next(a for a in theme.candidates(theme.subjects[0]) if a.id == "cycle:VER:LEC")
    assert cycle.arguments["driver_stop"] == 2 and cycle.label.startswith("2e cycle")


def test_a_race_the_question_does_not_name_is_asked_for_among_those_raced(data: RaceData) -> None:
    answer = questions(data).ask("Combien d'arrêts Verstappen a-t-il faits en 2025 ?")

    assert (answer.route, answer.status) == ("data", "asked") and (answer.reason or "").startswith(
        "Sur quelle course ?"
    )
    assert [(c.label, c.season, c.round) for c in answer.choices] == [
        ("Grand Prix de Chine 2025", 2025, 2),
        ("Grand Prix d'Australie 2025", 2025, 1),
    ]  # Japan has no race yet


def test_the_race_chosen_comes_back_with_the_question(data: RaceData) -> None:
    theme = ScriptedTheme(data, ["stops:VER"], "Verstappen s'est arrêté au tour 3.")

    answer = questions(data, theme).ask(
        "Combien d'arrêts Verstappen a-t-il faits en 2025 ?", route="data", season=2025, round_number=2
    )

    assert answer.status == "answered" and answer.race is not None and answer.race.round == 2


def test_the_path_is_asked_when_the_question_says_both_or_neither(data: RaceData) -> None:
    answer = questions(data).ask("Leclerc avait-il le droit de s'arrêter au tour 5 en Chine 2025 ?")

    assert (answer.route, answer.status) == (None, "asked")
    assert [(c.label, c.route) for c in answer.choices] == [
        ("Le règlement", "rules"),
        ("Les données d'une course", "data"),
        ("Un débrief de course", "debrief"),
    ]


def test_a_debrief_is_only_routed(data: RaceData) -> None:
    answer = questions(data).ask("Débrief stratégique du GP de Chine 2025 pour Ferrari")

    assert (answer.route, answer.status, answer.debrief) == ("debrief", "debrief", None)
