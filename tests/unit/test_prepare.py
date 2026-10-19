"""The debriefs prepared after a race (LAB-204), batched with an agent simulated without a model: what is prepared,
what a rerun skips, what a failure or the budget leaves for the next run."""

from typing import Any

from core.agent import AgentState
from core.agent.graph import Run, Waiting
from core.agent.state import Spent
from f1.prepare import Prepared, batch, prepare

ENTRY = [
    {"code": "NOR", "name": "Lando Norris", "team": "McLaren"},
    {"code": "LEC", "name": "Charles Leclerc", "team": "Ferrari"},
    {"code": "PIA", "name": "Oscar Piastri", "team": "McLaren"},
    {"code": "HAM", "name": "Lewis Hamilton", "team": "Ferrari"},
]


class FakeAgent:
    """Stops at the plan, then at the review, spending 1,000 tokens; fails on the requests named in `failing`."""

    def __init__(self, failing: tuple[str, ...] = ()) -> None:
        self.runs: dict[str, Run] = {}
        self.plans: list[list[str]] = []
        self.failing = failing

    def start(self, request: str, *, thread_id: str, given: Any = None) -> Run:
        if request in self.failing:
            raise RuntimeError("gateway down")
        state = AgentState(request=request, given=dict(given or {}))
        plan = {"analyses": [{"id": "result", "selected": True}, {"id": "tyres:NOR", "selected": False}]}
        self.runs[thread_id] = Run(thread_id, state, Waiting("plan", plan))
        return self.runs[thread_id]

    def resume(self, thread_id: str, answer: Any) -> Run:
        self.plans.append(answer)
        state = self.runs[thread_id].state.model_copy(update={"spent": Spent(llm_calls=5, tokens=1000)})
        self.runs[thread_id] = Run(thread_id, state, Waiting("review", {}))
        return self.runs[thread_id]

    def get(self, thread_id: str) -> Run:
        return self.runs[thread_id]  # KeyError: no such request


def test_a_race_gives_the_moments_then_a_debrief_per_team_in_finishing_order() -> None:
    debriefs = batch(2025, 16, ENTRY, ["team", "moments"])

    assert [(item.category, item.target, item.request) for item in debriefs] == [
        ("moments", "", "Les moments qui ont fait la course"),
        ("team", "McLaren", "Débrief stratégique de McLaren"),
        ("team", "Ferrari", "Débrief stratégique de Ferrari"),
    ]
    assert debriefs[1].given == {"season": 2025, "round": 16, "prepared": "team", "teams": ["McLaren"],
                                 "drivers": ["NOR", "PIA"]}  # fmt: skip
    assert len(batch(2025, 16, ENTRY, ["driver"])) == 4
    # The same debrief of the same race, the same thread: a rerun finds it.
    assert debriefs[1].thread_id == batch(2025, 16, ENTRY, ["team"])[0].thread_id
    assert debriefs[1].thread_id != batch(2025, 17, ENTRY, ["team"])[0].thread_id


def test_each_debrief_runs_to_its_review_with_the_plan_the_agent_picked() -> None:
    agent = FakeAgent()

    report = prepare(agent, batch(2025, 16, ENTRY, ["team", "moments"]))

    assert [item.outcome for item in report.done] == ["prepared"] * 3
    assert {item.status for item in report.done} == {"waiting"}
    assert agent.plans == [["result"]] * 3
    assert report.tokens == 3000


def test_a_rerun_skips_what_is_prepared_and_starts_again_what_failed() -> None:
    agent = FakeAgent(failing=("Débrief stratégique de Ferrari",))
    debriefs = batch(2025, 16, ENTRY, ["team"])

    first = prepare(agent, debriefs)
    assert [(item.outcome, item.error) for item in first.done] == [
        ("prepared", ""),
        ("failed", "RuntimeError: gateway down"),
    ]

    agent.failing = ()
    second = prepare(agent, debriefs)
    assert [item.outcome for item in second.done] == ["skipped", "prepared"]
    assert "1 prepared, 1 already there, 0 failed" in second.markdown()


def test_no_debrief_starts_once_the_budget_is_spent() -> None:
    report = prepare(FakeAgent(), batch(2025, 16, ENTRY, ["driver"]), budget=2000)

    assert [item.outcome for item in report.done] == ["prepared", "prepared", "not_started", "not_started"]


def test_a_thread_id_names_its_race_and_target() -> None:
    one = Prepared(2025, 16, "team", "Ferrari", "Débrief stratégique de Ferrari", {})
    assert one.thread_id == Prepared(2025, 16, "team", "Ferrari", "autre texte", {"x": 1}).thread_id
