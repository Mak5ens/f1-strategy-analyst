"""The controlled agent's graph without a model (LAB-151): a theme of fakes, an in-memory checkpointer. The three
stops, the closed catalog, the check of every number, the drafts again, the limits, and a resume by a new agent."""

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from core.agent import (
    Agent,
    AgentLimits,
    AgentState,
    Analysis,
    Clarification,
    Event,
    Option,
    Point,
    Result,
    Rule,
    RuleSource,
    check_point,
)
from core.agent.state import serializer
from core.tools import ToolError
from core.tracing import Tracer


class FakeTheme:
    """A theme of a race weekend: the request names a race, or asks for "the last one", which is ambiguous."""

    name = "test"

    def __init__(self, drafts: Sequence[list[Point]] | None = None) -> None:
        self.drafts = list(drafts or [])
        self.problems_seen: list[Mapping[str, Sequence[str]]] = []
        self.published: list[str] = []

    def parse(self, request: str, *, session_id: str | None) -> dict[str, Any]:
        return {"race": None if "dernier" in request else "Monza"}

    def resolve(self, subject: Mapping[str, Any]) -> dict[str, Any] | Clarification:
        if subject.get("race"):
            return {**subject, "round": 16}
        options = [
            Option(label="Monza 2025", value={"race": "Monza"}),
            Option(label="Bakou 2025", value={"race": "Bakou"}),
        ]
        return Clarification(field="race", question="Quelle course ?", options=options)

    def answer(self, subject: Mapping[str, Any], clarification: Clarification) -> dict[str, Any]:
        chosen = next(option for option in clarification.options if option.label == clarification.answer)
        return {**subject, **chosen.value}

    def candidates(self, subject: Mapping[str, Any]) -> list[Analysis]:
        return [
            Analysis(id="loss:LEC", tool="pit_stop_loss", arguments={"driver": "LEC"}, label="Arrêts de Leclerc"),
            Analysis(id="loss:HAM", tool="pit_stop_loss", arguments={"driver": "HAM"}, label="Arrêts de Hamilton"),
            Analysis(id="sc", tool="neutralizations", arguments={}, label="Neutralisations"),
        ]

    def choose(
        self, request: str, subject: Mapping[str, Any], candidates: Sequence[Analysis], *, session_id: str | None
    ) -> list[str]:
        return ["loss:LEC", "sc", "invented"]  # an id outside the catalog is dropped

    def run(self, analysis: Analysis) -> dict[str, Any]:
        if analysis.id == "loss:HAM":
            raise ToolError("no pit stop for HAM in round 16")
        if analysis.id == "sc":
            return {"periods": [{"kind": "SC", "laps": [23, 25]}]}
        return {"stops": [{"lap": 23, "time_lost_s": 21.4}]}

    def events(self, subject: Mapping[str, Any], results: Sequence[Result]) -> list[Event]:
        return [Event(id="E1", kind="SC", summary="Voiture de sécurité, tours 23 à 25", question="Arrêts sous SC ?")]

    def rule(self, event: Event, *, session_id: str | None) -> Rule:
        source = RuleSource(id=f"{event.id}:S1", label="Article 55.14", text="Pit stops are allowed under SC.")
        return Rule(event=event.id, question=event.question, answered=True, claims=["Autorisé"], sources=[source])

    def draft(
        self,
        request: str,
        subject: Mapping[str, Any],
        results: Sequence[Result],
        rules: Sequence[Rule],
        problems: Mapping[str, Sequence[str]],
        *,
        session_id: str | None,
    ) -> list[Point]:
        self.problems_seen.append(problems)
        if self.drafts:
            return self.drafts.pop(0)
        return [
            Point(id="P1", text="Leclerc a perdu 21.4 s au tour 23.", facts=["loss:LEC"]),
            Point(id="P2", text="Arrêt autorisé sous voiture de sécurité.", sources=["E1:S1"]),
        ]

    def unavailable(self, result: Result) -> Point:
        return Point(id=f"NA-{result.id}", text=f"Donnée indisponible : {result.label}", status="unavailable")

    def render(self, subject: Mapping[str, Any], points: Sequence[Point], rules: Sequence[Rule]) -> str:
        return "\n".join(f"- {point.text}" for point in points)

    def check(self, point: Point) -> list[str]:
        return ["a number in words"] if "deux tours" in point.text else []


def agent(theme: FakeTheme, saver: InMemorySaver | None = None, **limits: Any) -> Agent:
    published: list[str] = theme.published
    return Agent(
        theme,
        checkpointer=saver or InMemorySaver(serde=serializer()),
        tracer=Tracer(None),
        limits=AgentLimits(_env_file=None, **limits),
        on_publish=lambda thread, state: published.append(thread),
    )


def test_a_request_stops_for_the_plan_then_the_review_then_publishes() -> None:
    theme = FakeTheme()
    bot = agent(theme)

    run = bot.start("Débrief de Monza", thread_id="t1")
    assert run.waiting is not None and run.waiting.kind == "plan"
    # The model's choice, within the catalog; a person can still add what it left out.
    assert [(a["id"], a["selected"]) for a in run.waiting.payload["analyses"]] == [
        ("loss:LEC", True), ("loss:HAM", False), ("sc", True),
    ]  # fmt: skip

    run = bot.resume("t1", ["loss:LEC", "loss:HAM", "sc"])
    assert run.waiting is not None and run.waiting.kind == "review"
    points = {point["id"]: point for point in run.waiting.payload["points"]}
    assert points["P1"]["status"] == "verified" and points["P2"]["status"] == "verified"
    # The analysis that failed gives no number: its point says so.
    assert points["NA-loss:HAM"] == {**points["NA-loss:HAM"], "status": "unavailable"}

    decisions = [
        {"point": "P1", "action": "approve"},
        {"point": "P2", "action": "correct", "text": "Arrêt permis sous SC (article 55.14).", "reason": "wording"},
        {"point": "NA-loss:HAM", "action": "reject", "reason": "off_topic"},
    ]
    run = bot.resume("t1", decisions)
    assert run.status == "published" and theme.published == ["t1"]
    assert run.state.deliverable == "- Leclerc a perdu 21.4 s au tour 23.\n- Arrêt permis sous SC (article 55.14)."
    assert run.state.spent.steps == 12  # one per node, none for the clarification it did not need


def test_an_ambiguous_request_asks_instead_of_guessing() -> None:
    bot = agent(FakeTheme())
    run = bot.start("Débrief du dernier GP", thread_id="t2")
    assert run.waiting is not None and run.waiting.kind == "clarification"
    assert [option["label"] for option in run.waiting.payload["options"]] == ["Monza 2025", "Bakou 2025"]

    run = bot.resume("t2", "Silverstone")  # not an option: asked again
    assert run.waiting is not None and run.waiting.kind == "clarification"
    run = bot.resume("t2", 1)  # an option's index works too
    assert run.waiting is not None and run.waiting.kind == "plan"
    assert run.state.subject == {"race": "Bakou", "round": 16}
    assert run.state.clarifications[0].answer == "Bakou 2025"


def test_a_number_from_no_analysis_sends_the_point_back_to_draft() -> None:
    invented = [Point(id="P1", text="Leclerc a perdu 19.0 s au tour 23.", facts=["loss:LEC"])]
    fixed = [Point(id="P1", text="Leclerc a perdu 21.4 s au tour 23.", facts=["loss:LEC"])]
    theme = FakeTheme(drafts=[invented, fixed])
    bot = agent(theme)
    bot.start("Débrief de Monza", thread_id="t3")
    run = bot.resume("t3", ["loss:LEC"])
    assert run.state.drafts == 2
    assert "19.0" in next(iter(theme.problems_seen[1].values()))[0]  # the second draft is told what was wrong
    assert run.state.points[0].status == "verified"


def test_the_theme_adds_its_own_checks() -> None:
    words = [Point(id="P1", text="Leclerc s'est arrêté deux tours plus tard.", facts=["loss:LEC"])]
    bot = agent(FakeTheme(drafts=[words] * 3))
    bot.start("Débrief de Monza", thread_id="t8")
    run = bot.resume("t8", ["loss:LEC"])
    assert run.state.points[0].problems == ["a number in words"]


def test_a_point_never_backed_reaches_the_person_marked_unverified() -> None:
    invented = [Point(id="P1", text="Leclerc a perdu 19.0 s.", facts=["loss:LEC"])]
    bot = agent(FakeTheme(drafts=[invented] * 3), drafts=3)
    bot.start("Débrief de Monza", thread_id="t4")
    run = bot.resume("t4", ["loss:LEC"])
    assert run.waiting is not None and run.waiting.kind == "review" and run.state.drafts == 3
    assert run.state.points[0].status == "unverified"


def test_every_point_needs_a_decision_and_a_correction_its_text() -> None:
    bot = agent(FakeTheme())
    bot.start("Débrief de Monza", thread_id="t5")
    bot.resume("t5", ["loss:LEC"])
    run = bot.resume("t5", [{"point": "P1", "action": "approve"}])  # P2 is not decided
    assert run.waiting is not None and run.waiting.kind == "review"
    run = bot.resume("t5", [{"point": "P1", "action": "approve"}, {"point": "P2", "action": "correct"}])
    assert run.waiting is not None and run.waiting.kind == "review"


def test_a_request_over_its_limits_stops_and_says_why() -> None:
    run = agent(FakeTheme(), max_steps=2).start("Débrief de Monza", thread_id="t6")
    assert run.status == "stopped" and run.state.stop_reason == "2 steps, the limit"


def test_a_new_agent_on_the_same_checkpoints_resumes_a_waiting_request() -> None:
    saver = InMemorySaver(serde=serializer())
    agent(FakeTheme(), saver).start("Débrief de Monza", thread_id="t7")
    restarted = agent(FakeTheme(), saver)  # a restart: a new process, the same database
    run = restarted.get("t7")
    assert run.waiting is not None and run.waiting.kind == "plan"
    assert restarted.resume("t7", ["sc"]).waiting.kind == "review"  # type: ignore[union-attr]


def test_a_point_is_checked_against_what_it_cites_only() -> None:
    results = {
        "loss": Result(id="loss", tool="t", label="l", arguments={}, output={"time_lost_s": 21.37}),
        "gap": Result(id="gap", tool="t", label="l", arguments={}, error="no data"),
    }
    sources = {"E1:S1": RuleSource(id="E1:S1", label="Art. 55", text="a 5 second penalty")}
    subject = {"season": 2025}

    def problems(point: Point) -> list[str]:
        return check_point(point, results, sources, subject)

    assert (
        problems(Point(id="p", text="21.4 s perdues en 2025, pénalité de 5 s", facts=["loss"], sources=["E1:S1"])) == []
    )
    assert "21.4" in problems(Point(id="p", text="21.4 s perdues", facts=[]))[0]  # the number's analysis is not cited
    assert problems(Point(id="p", text="Écart", facts=["gap"])) == [
        "cites analyses that failed and gave no number: gap"
    ]
    assert problems(Point(id="p", text="Voir", sources=["E9:S1"])) == ["cites sources that were not retrieved: E9:S1"]


def test_the_state_round_trips_through_json() -> None:
    state = AgentState(request="r", points=[Point(id="P1", text="t")])
    assert AgentState.model_validate_json(state.model_dump_json()) == state


@pytest.fixture(autouse=True)
def no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("AGENT_MAX_STEPS", "AGENT_MAX_LLM_CALLS", "AGENT_MAX_TOKENS", "AGENT_DRAFTS"):
        monkeypatch.delenv(name, raising=False)
