"""Questions on a published deliverable (LAB-205) without a model: a fake theme whose replies are scripted. An answer
with an unbacked number is written again once, then withheld; another subject is refused before any model call."""

from collections.abc import Mapping, Sequence
from typing import Any

from core.agent import AgentState, Analysis, Event, Point, Result, Rule, RuleSource
from core.agent.chat import Chat, ChatLimits, Exchange, Pick
from core.tracing import Tracer

STATE = AgentState(
    request="Débrief de Monza pour Ferrari",
    subject={"race": "Monza"},
    results=[
        Result(id="loss:LEC", tool="pit_stop_loss", label="Arrêts de Leclerc", arguments={},
               output={"stops": [{"lap": 33, "time_lost_s": 24.8}]}),
    ],
)  # fmt: skip


class FakeChatTheme:
    name = "test"

    def __init__(self, replies: Sequence[list[Point]], pick: Pick | None = None) -> None:
        self.replies = list(replies)
        self._pick = pick or Pick()
        self.picked = 0
        self.problems_seen: list[Mapping[str, Sequence[str]]] = []
        self.ran: list[str] = []

    def scope(self, subject: Mapping[str, Any], question: str) -> str | None:
        return "Posez-la depuis la page de Bakou." if "Bakou" in question else None

    def candidates(self, subject: Mapping[str, Any]) -> list[Analysis]:
        return [
            Analysis(id="loss:LEC", tool="pit_stop_loss", arguments={}, label="Arrêts de Leclerc"),
            Analysis(id="tyres:LEC", tool="stint_degradation", arguments={}, label="Pneus de Leclerc"),
        ]

    def run(self, analysis: Analysis) -> dict[str, Any]:
        self.ran.append(analysis.id)
        return {"stints": [{"degradation_s_per_lap": 0.071}]}

    def pick(self, question: str, subject: Mapping[str, Any], candidates: Sequence[Analysis],
             history: Sequence[Exchange], *, session_id: str | None) -> Pick:  # fmt: skip
        self.picked += 1
        return self._pick

    def rule(self, event: Event, *, session_id: str | None) -> Rule:
        source = RuleSource(id="Q:S1", label="Article 55.14", text="Pit stops under SC: 2 laps at most.")
        return Rule(event=event.id, question=event.question, answered=True, sources=[source])

    def reply(self, question: str, subject: Mapping[str, Any], results: Sequence[Result], rules: Sequence[Rule],
              history: Sequence[Exchange], problems: Mapping[str, Sequence[str]], *,
              session_id: str | None) -> list[Point]:  # fmt: skip
        self.problems_seen.append(problems)
        return self.replies.pop(0)

    def check(self, point: Point) -> list[str]:
        return []

    def faithful(
        self, point: Point, results: Sequence[Result], sources: Sequence[RuleSource], *, session_id: str | None
    ) -> list[str]:
        return ["sens : l'arrêt était sous voiture de sécurité"] if "en course" in point.text else []


def chat(theme: FakeChatTheme, **limits: Any) -> Chat:
    return Chat(theme, tracer=Tracer(None), limits=ChatLimits(_env_file=None, **limits))


def test_an_answer_whose_numbers_are_backed_is_shown() -> None:
    theme = FakeChatTheme([[Point(id="A1", text="Leclerc a perdu 24.8 s au tour 33.", facts=["loss:LEC"])]])

    reply = chat(theme).ask("Combien a coûté l'arrêt de Leclerc ?", state=STATE)

    assert reply.status == "answered" and reply.points[0].status == "verified"
    assert reply.results == [] and theme.ran == []  # the deliverable's analysis was enough


def test_a_reply_its_analyses_contradict_is_withheld() -> None:
    wrong = [Point(id="A1", text="Leclerc a perdu 24.8 s en course au tour 33.", facts=["loss:LEC"])]

    reply = chat(FakeChatTheme([wrong, wrong])).ask("Combien a coûté l'arrêt de Leclerc ?", state=STATE)

    assert reply.status == "withheld" and "voiture de sécurité" in (reply.reason or "")


def test_a_wrong_number_is_written_again_then_withheld() -> None:
    wrong = [Point(id="A1", text="Leclerc a perdu 31.2 s au tour 33.", facts=["loss:LEC"])]
    theme = FakeChatTheme([wrong, wrong])

    reply = chat(theme).ask("Combien a coûté l'arrêt de Leclerc ?", state=STATE)

    assert reply.status == "withheld" and reply.points == []
    assert "31.2" in (reply.reason or "")
    assert theme.problems_seen[1]  # the second reply was told what was wrong


def test_a_second_reply_that_fixes_the_number_is_shown() -> None:
    wrong = [Point(id="A1", text="Leclerc a perdu 31.2 s.", facts=["loss:LEC"])]
    right = [Point(id="A1", text="Leclerc a perdu 24.8 s.", facts=["loss:LEC"])]

    reply = chat(FakeChatTheme([wrong, right])).ask("Combien ?", state=STATE)

    assert reply.status == "answered" and reply.points[0].text == "Leclerc a perdu 24.8 s."


def test_more_analyses_come_from_the_catalog_only_and_rules_from_the_retrieval() -> None:
    pick = Pick(analyses=["tyres:LEC", "loss:LEC", "cycle:LEC:SAI"], rule_question="Arrêts sous voiture de sécurité ?")
    answer = [Point(id="A1", text="0.071 s par tour ; 2 tours au plus.", facts=["tyres:LEC"], sources=["Q:S1"])]
    theme = FakeChatTheme([answer], pick)

    reply = chat(theme).ask("Et ses pneus, sous voiture de sécurité ?", state=STATE)

    assert theme.ran == ["tyres:LEC"]  # not the one already run, not one outside the catalog
    assert [result.id for result in reply.results] == ["tyres:LEC"] and reply.rules[0].sources[0].id == "Q:S1"
    assert reply.status == "answered"


def test_another_race_is_refused_before_any_model_call() -> None:
    theme = FakeChatTheme([])

    reply = chat(theme).ask("Et à Bakou ?", state=STATE)

    assert (reply.status, reply.reason) == ("refused", "Posez-la depuis la page de Bakou.")
    assert theme.picked == 0


def test_a_question_stops_at_its_limit() -> None:
    reply = chat(FakeChatTheme([]), max_llm_calls=0).ask("Combien ?", state=STATE)

    assert reply.status == "stopped" and "limit" in (reply.reason or "")
