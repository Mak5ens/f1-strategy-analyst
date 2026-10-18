"""Acceptance of the debrief agent (LAB-151), on PostgreSQL, the lake, the FIA index and the gateway's chat-pro.

- A restart during each of the three waits loses nothing: a new agent on the same database goes on.
- A whole debrief of a Grand Prix has no number that does not come from an analysis.
- An ambiguous request ("le dernier GP") asks instead of guessing.
- A question on a race chosen from its page (LAB-203) is never asked which race, answers first, every number backed,
  and ends on what the data cannot say.
- A question on a published debrief (LAB-205) is answered with backed numbers only, and another race is refused.
"""

import uuid
from collections.abc import Iterator

import pytest

from core.agent import Agent, AgentState
from core.agent.store import PublishedStore
from core.numbers import unverified_numbers
from f1.agent import debrief_agent, debrief_chat
from f1.data import connect

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def data() -> None:
    if not connect().execute("SELECT 1 FROM sessions WHERE season = 2025 AND round = 16").fetchall():
        pytest.skip("2025 not in the lake: run `just ingest 2025`")


@pytest.fixture
def agent() -> Iterator[Agent]:
    with debrief_agent() as agent:
        yield agent


def test_an_ambiguous_request_asks_which_race(agent: Agent) -> None:
    run = agent.start("Débrief stratégique du dernier GP", thread_id=str(uuid.uuid4()))
    assert run.waiting is not None and run.waiting.kind == "clarification"
    assert len(run.waiting.payload["options"]) > 1


def test_a_debrief_survives_a_restart_at_each_stop_and_every_number_is_backed() -> None:
    # Each `with` is a new agent on a new connection to the same database: a restart of the service.
    thread = str(uuid.uuid4())
    with debrief_agent() as agent:
        run = agent.start("Débrief du Grand Prix d'Italie pour Ferrari", thread_id=thread)
        assert run.waiting is not None and run.waiting.kind == "clarification"  # no season: which one?
    with debrief_agent() as agent:  # restarted while waiting for the clarification
        options = [option["label"] for option in agent.get(thread).waiting.payload["options"]]  # type: ignore[union-attr]
        run = agent.resume(thread, options.index("Grand Prix d'Italie 2025"))
        assert run.waiting is not None and run.waiting.kind == "plan"
    with debrief_agent() as agent:  # restarted while waiting for the plan
        plan = agent.get(thread).waiting.payload["analyses"]  # type: ignore[union-attr]
        run = agent.resume(thread, [analysis["id"] for analysis in plan if analysis["selected"]])
        assert run.waiting is not None and run.waiting.kind == "review"
    with debrief_agent() as agent:  # restarted while waiting for the review
        run = agent.get(thread)
        points = run.waiting.payload["points"]  # type: ignore[union-attr]
        run = agent.resume(thread, [{"point": point["id"], "action": "approve"} for point in points])

    assert run.status == "published", run.state.stop_reason
    assert_backed(run.state)
    published = PublishedStore().get(thread)
    assert published is not None and published["deliverable"] == run.state.deliverable


def test_a_question_on_a_chosen_race_answers_first(agent: Agent) -> None:
    # Singapore 2024: Hamilton started on softs, one of 2 cars to do so, from 3rd on the grid.
    given = {"season": 2024, "round": 18, "question": True}
    run = agent.start("Pourquoi Hamilton est-il parti en pneus tendres ?", thread_id=str(uuid.uuid4()), given=given)
    assert run.waiting is not None and run.waiting.kind == "plan"  # the race is not asked for
    plan = {analysis["id"]: analysis for analysis in run.waiting.payload["analyses"]}
    assert plan["strategies"]["selected"] and "stops:HAM" in plan

    run = agent.resume(run.thread_id, [id_ for id_, analysis in plan.items() if analysis["selected"]])

    assert run.waiting is not None and run.waiting.kind == "review", run.state.stop_reason
    points = run.state.points
    assert "tendre" in points[0].text.lower() and "strategies" in points[0].facts
    assert not any(char.isdigit() for char in points[-1].text)  # what the data cannot say: no number
    assert all(point.status == "verified" for point in points), [point.problems for point in points]


def test_questions_on_the_ferrari_debrief_of_monza(agent: Agent) -> None:
    given = {"season": 2025, "round": 16}
    run = agent.start("Débrief stratégique pour Ferrari", thread_id=str(uuid.uuid4()), given=given)
    assert run.waiting is not None and run.waiting.kind == "plan"
    plan = run.waiting.payload["analyses"]
    run = agent.resume(run.thread_id, [analysis["id"] for analysis in plan if analysis["selected"]])
    assert run.waiting is not None, run.state.stop_reason
    run = agent.resume(run.thread_id, [{"point": p.id, "action": "approve"} for p in run.state.points])
    assert run.status == "published"
    chat = debrief_chat()

    reply = chat.ask("Détaille le cycle d'arrêts de Leclerc face à Russell", state=run.state)
    refused = chat.ask("Et au Grand Prix de Monaco ?", state=run.state)

    assert reply.status in {"answered", "withheld"}, reply.reason
    if reply.status == "answered":  # what is shown is backed, every number
        assert reply.points and all(point.status == "verified" for point in reply.points)
    assert refused.status == "refused" and refused.spent.llm_calls == 0


def test_a_free_question_on_monza_is_routed_to_its_data_and_answered_with_checked_numbers() -> None:
    from f1.grand_prix import GrandPrix
    from f1.questions import FreeQuestions
    from f1.rag import rag_pipeline
    from f1.router import Router

    grand_prix = GrandPrix(connect())
    chat = debrief_chat()
    questions = FreeQuestions(Router(*grand_prix.people()), grand_prix, rules=rag_pipeline, chat=lambda: chat)

    answer = questions.ask("Quel écart entre Leclerc et Russell au tour 20 du GP d'Italie 2025 ?")

    assert (answer.route, answer.race and answer.race.round) == ("data", 16)
    assert answer.status in {"answered", "withheld"}, answer.reason
    if answer.status == "answered":
        assert [fact.id for fact in answer.facts] == ["gap:LEC:RUS"]


def assert_backed(state: AgentState) -> None:
    results = {result.id: result for result in state.results}
    sources = {source.id: source.text for rule in state.rules for source in rule.sources}
    for point in state.points:
        if point.status == "unavailable":
            continue
        data = [results[fact].output for fact in point.facts] + [sources[s] for s in point.sources] + [state.subject]
        assert point.status == "verified", (point.text, point.problems)
        assert unverified_numbers(point.text, data) == [], point.text
