"""Acceptance of the debrief agent (LAB-151), on PostgreSQL, the lake, the FIA index and the gateway's chat-pro.

- A restart during each of the three waits loses nothing: a new agent on the same database goes on.
- A whole debrief of a Grand Prix has no number that does not come from an analysis.
- An ambiguous request ("le dernier GP") asks instead of guessing.
"""

import uuid
from collections.abc import Iterator

import pytest

from core.agent import Agent, AgentState
from core.agent.store import PublishedStore
from core.numbers import unverified_numbers
from f1.agent import debrief_agent
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
        run = agent.resume(thread, options.index("Italian Grand Prix 2025"))
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


def assert_backed(state: AgentState) -> None:
    results = {result.id: result for result in state.results}
    sources = {source.id: source.text for rule in state.rules for source in rule.sources}
    for point in state.points:
        if point.status == "unavailable":
            continue
        data = [results[fact].output for fact in point.facts] + [sources[s] for s in point.sources] + [state.subject]
        assert point.status == "verified", (point.text, point.problems)
        assert unverified_numbers(point.text, data) == [], point.text
