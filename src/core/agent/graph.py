"""A controlled agent: a fixed graph, whose routing is code, where a model only fills bounded nodes (LAB-151).

    parse -> resolve -> [clarify -> resolve]* -> plan -> approve_plan -> run_tools -> detect_events
          -> retrieve_rules -> draft -> verify -> [draft -> verify]* -> review -> apply -> publish

A theme fills the nodes (`Theme`): what a request asks, which analyses its closed catalog holds, what events a rule
explains, how a deliverable is written. The graph decides the rest, the same for every theme:

- **Three stops for a person**, as LangGraph interrupts: a clarification instead of a guess, the plan before any
  analysis runs, and the review of every point before anything is published. The state is saved after each node
  (the checkpointer), so a request waiting for a person survives a restart.
- **Numbers come from analyses only.** `verify` is code: each number of a point must be in the outputs of the
  analyses the point cites (or in a rule source it cites), each source must be one the retrieval found. A point that
  fails goes back to `draft`, at most `AGENT_DRAFTS` drafts in all, then is marked unverified for the person; the
  theme adds its own checks (`Theme.check`: numbers written in words, which no check could match). A failed
  analysis never yields a number: its point says the data is unavailable.
- **Limits per request**: steps, model calls and tokens, on top of the gateway's budget of the team; over a limit,
  the request stops, and says which.
- **One span per node** in Langfuse, with its input, its output and its routing decision, all in one trace for the
  whole request, resumes included.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import TypeAdapter, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.agent.state import (
    AgentState,
    Analysis,
    Clarification,
    Decision,
    Event,
    Point,
    Result,
    Rule,
    RuleSource,
)
from core.gateway import usage_scope
from core.numbers import unverified_numbers
from core.tools import ToolError
from core.tracing import Tracer


class AgentLimits(BaseSettings):
    """Read from the environment with the `AGENT_` prefix: what one request may use."""

    model_config = SettingsConfigDict(env_prefix="AGENT_", env_file=".env", extra="ignore")

    max_steps: int = 40  # nodes run, clarifications and drafts again included
    max_llm_calls: int = 80  # chat calls, the retrieval pipeline's included
    max_tokens: int = 300_000
    drafts: int = 3  # the first draft and two more after a failed verification
    max_events: int = 4  # rule questions asked to the retrieval pipeline
    max_analyses: int = 16


class Theme(Protocol):
    """What a theme gives the graph: the content of each node. Every method but `parse`, `choose`, `rule` and
    `draft` is code; those four may call a model, and must validate what it returns."""

    name: str

    def parse(self, request: str, *, session_id: str | None) -> dict[str, Any]:
        """What the request is about, as the theme's subject."""
        ...

    def resolve(self, subject: Mapping[str, Any]) -> dict[str, Any] | Clarification:
        """The subject checked against the data, or the question to ask a person when it is ambiguous or unknown."""
        ...

    def answer(self, subject: Mapping[str, Any], clarification: Clarification) -> dict[str, Any]:
        """The subject with a person's answer to a clarification."""
        ...

    def candidates(self, subject: Mapping[str, Any]) -> list[Analysis]:
        """The closed catalog of analyses for this subject: tools and arguments decided by code."""
        ...

    def choose(
        self, request: str, subject: Mapping[str, Any], candidates: Sequence[Analysis], *, session_id: str | None
    ) -> list[str]:
        """The ids of the candidates that fit the request (a model may only pick among them)."""
        ...

    def run(self, analysis: Analysis) -> dict[str, Any]:
        """The analysis's output; `ToolError` when the data cannot answer it."""
        ...

    def events(self, subject: Mapping[str, Any], results: Sequence[Result]) -> list[Event]:
        """What a rule explains in the results, each with its question."""
        ...

    def rule(self, event: Event, *, session_id: str | None) -> Rule:
        """The retrieval pipeline's answer to an event's question."""
        ...

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
        """The points of the deliverable; `problems` are those `verify` found in the previous draft, by its text."""
        ...

    def unavailable(self, result: Result) -> Point:
        """The point that says an analysis could not be computed."""
        ...

    def check(self, point: Point) -> list[str]:
        """The theme's own checks of a point, on top of the graph's (a number written in words escapes those)."""
        ...

    def render(self, subject: Mapping[str, Any], points: Sequence[Point], rules: Sequence[Rule]) -> str:
        """The deliverable, once reviewed."""
        ...


def check_point(
    point: Point, results: Mapping[str, Result], sources: Mapping[str, RuleSource], subject: Mapping[str, Any]
) -> list[str]:
    """What is wrong with a point, one sentence each; empty when every number and source is backed."""
    problems = []
    if unknown := [fact for fact in point.facts if fact not in results]:
        problems.append(f"cites analyses that do not exist: {', '.join(unknown)}")
    if failed := [fact for fact in point.facts if fact in results and not results[fact].ok]:
        problems.append(f"cites analyses that failed and gave no number: {', '.join(failed)}")
    if unknown_sources := [source for source in point.sources if source not in sources]:
        problems.append(f"cites sources that were not retrieved: {', '.join(unknown_sources)}")
    data: list[Any] = [results[fact].output for fact in point.facts if fact in results and results[fact].ok]
    data += [sources[source].text for source in point.sources if source in sources]
    data.append(dict(subject))
    if numbers := unverified_numbers(point.text, data):
        problems.append(
            f"numbers that are in none of the analyses or sources it cites: {', '.join(numbers)} "
            "(copy each number from a cited analysis, as written there, and cite that analysis)"
        )
    return problems


@dataclass(frozen=True)
class Waiting:
    """What a person must answer for the request to go on."""

    kind: str  # "clarification", "plan" or "review"
    payload: dict[str, Any]


@dataclass(frozen=True)
class Run:
    thread_id: str
    state: AgentState
    waiting: Waiting | None

    @property
    def status(self) -> str:
        return "waiting" if self.waiting else self.state.status


Node = Callable[[AgentState, str], dict[str, Any]]  # the state and the request's thread id


class GraphNode(Protocol):
    """A node as LangGraph calls it, with the run's config."""

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]: ...


class Agent:
    """The graph of a theme, compiled with a checkpointer: start a request, resume it with a person's answer."""

    def __init__(
        self,
        theme: Theme,
        *,
        checkpointer: BaseCheckpointSaver[Any],
        tracer: Tracer,
        limits: AgentLimits | None = None,
        on_publish: Callable[[str, AgentState], None] | None = None,
        on_run: Callable[[Run], None] | None = None,
    ) -> None:
        self.theme = theme
        self.tracer = tracer
        self.limits = limits or AgentLimits()
        self._on_publish = on_publish
        self._on_run = on_run
        self.graph = self._build().compile(checkpointer=checkpointer)

    # Requests

    def start(self, request: str, *, thread_id: str, given: Mapping[str, Any] | None = None) -> Run:
        """Run a request to its first stop. `given` holds subject fields the person chose rather than wrote."""
        state = AgentState(request=request, trace_id=self.tracer.new_trace_id(), given=dict(given or {}))
        try:
            self.graph.invoke(state, self._config(thread_id))
        finally:
            self.tracer.flush()  # the spans leave before a person, or a restart, makes the request wait
        return self._ran(thread_id)

    def resume(self, thread_id: str, answer: Any) -> Run:
        if self.get(thread_id).waiting is None:
            raise ValueError(f"{thread_id} is not waiting for an answer")
        try:
            self.graph.invoke(Command(resume=answer), self._config(thread_id))
        finally:
            self.tracer.flush()
        return self._ran(thread_id)

    def get(self, thread_id: str) -> Run:
        snapshot = self.graph.get_state(self._config(thread_id))
        if not snapshot.values:
            raise KeyError(f"no request {thread_id}")
        interrupts = [item for task in snapshot.tasks for item in task.interrupts]
        waiting = Waiting(interrupts[0].value["kind"], interrupts[0].value) if interrupts else None
        return Run(thread_id, AgentState.model_validate(snapshot.values), waiting)

    def _ran(self, thread_id: str) -> Run:
        run = self.get(thread_id)
        if self._on_run is not None:
            self._on_run(run)
        return run

    def _config(self, thread_id: str) -> RunnableConfig:
        # Each node is a step; LangGraph's own limit only backs up the agent's.
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": self.limits.max_steps * 2 + 10}

    # The graph

    def _build(self) -> StateGraph[AgentState]:
        nodes: list[tuple[str, Node, str]] = [
            ("parse", self._parse, "resolve"),
            ("resolve", self._resolve, "plan"),
            ("clarify", self._clarify, "resolve"),
            ("plan", self._plan, "approve_plan"),
            ("approve_plan", self._approve_plan, "run_tools"),
            ("run_tools", self._run_tools, "detect_events"),
            ("detect_events", self._detect_events, "retrieve_rules"),
            ("retrieve_rules", self._retrieve_rules, "draft"),
            ("draft", self._draft, "verify"),
            ("verify", self._verify, "review"),
            ("review", self._review, "apply"),
            ("apply", self._apply, "publish"),
            ("publish", self._publish, END),
        ]
        graph = StateGraph(AgentState)
        names = [name for name, _, _ in nodes]
        for name, function, default in nodes:
            graph.add_node(name, self._traced(name, function, default))
            graph.add_conditional_edges(name, _route, [*names, END])
        graph.add_edge(START, "parse")
        return graph

    def _traced(self, name: str, function: Node, default: str) -> GraphNode:
        """The node within its span and its usage count, after a check of the request's limits. Its routing
        decision is `next`, `default` unless the node chose another."""

        def node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
            if reason := self._over_limits(state):
                return {"status": "stopped", "stop_reason": reason, "next": END}
            with (
                self.tracer.trace(f"{self.theme.name}.{name}", _brief(state), trace_id=state.trace_id),
                usage_scope() as usage,
            ):
                try:
                    update = function(state, config["configurable"]["thread_id"])
                except GraphInterrupt:
                    self.tracer.output({"waiting": name})
                    raise
                update.setdefault("next", default)
                self.tracer.output(_plain(update))
            spent = state.spent.model_copy(
                update={
                    "steps": state.spent.steps + 1,
                    "llm_calls": state.spent.llm_calls + usage.calls,
                    "tokens": state.spent.tokens + usage.tokens,
                }
            )
            return {**update, "spent": spent}

        return node

    def _over_limits(self, state: AgentState) -> str | None:
        spent, limits = state.spent, self.limits
        if spent.steps >= limits.max_steps:
            return f"{spent.steps} steps, the limit"
        if spent.llm_calls >= limits.max_llm_calls:
            return f"{spent.llm_calls} model calls, the limit"
        if spent.tokens >= limits.max_tokens:
            return f"{spent.tokens} tokens, over the limit of {limits.max_tokens}"
        return None

    # Nodes

    def _parse(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        return {"subject": {**self.theme.parse(state.request, session_id=state.trace_id), **state.given}}

    def _resolve(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        resolved = self.theme.resolve(state.subject)
        if isinstance(resolved, Clarification):
            return {"clarification": resolved, "next": "clarify"}
        return {"subject": resolved, "clarification": None}

    def _clarify(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        assert state.clarification is not None
        question = state.clarification
        answer = interrupt({"kind": "clarification", **question.model_dump(exclude={"answer"})})
        labels = [option.label for option in question.options]
        if isinstance(answer, int) and 0 <= answer < len(labels):
            answer = labels[answer]
        if answer not in labels:  # asked again: an answer outside the options is not a guess either
            return {"next": "clarify"}
        answered = question.model_copy(update={"answer": answer})
        return {
            "subject": self.theme.answer(state.subject, answered),
            "clarifications": [*state.clarifications, answered],
            "clarification": None,
        }

    def _plan(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        candidates = self.theme.candidates(state.subject)[: self.limits.max_analyses]
        ids = {analysis.id for analysis in candidates}
        chosen = set(self.theme.choose(state.request, state.subject, candidates, session_id=state.trace_id))
        chosen &= ids  # the model picks in the catalog, or nothing
        return {"plan": [analysis.model_copy(update={"selected": analysis.id in chosen}) for analysis in candidates]}

    def _approve_plan(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        answer = interrupt({"kind": "plan", "analyses": [analysis.model_dump() for analysis in state.plan]})
        try:
            selected = set(TypeAdapter(list[str]).validate_python(answer))
        except ValidationError:
            return {"next": "approve_plan"}
        return {
            "plan": [analysis.model_copy(update={"selected": analysis.id in selected}) for analysis in state.plan],
            "plan_approved": True,
        }

    def _run_tools(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        results = []
        for analysis in state.plan:
            if not analysis.selected:
                continue
            result = Result(id=analysis.id, tool=analysis.tool, label=analysis.label, arguments=analysis.arguments)
            try:
                result.output = self.theme.run(analysis)
            except ToolError as error:
                result.error = str(error)
            except Exception as error:  # a bug of a tool is no number either
                result.error = f"{type(error).__name__}: {error}"
            results.append(result)
        return {"results": results}

    def _detect_events(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        return {"events": self.theme.events(state.subject, state.results)[: self.limits.max_events]}

    def _retrieve_rules(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        return {"rules": [self.theme.rule(event, session_id=state.trace_id) for event in state.events]}

    def _draft(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        problems = {point.text: point.problems for point in state.points if point.problems}
        ok = [result for result in state.results if result.ok]
        points = self.theme.draft(state.request, state.subject, ok, state.rules, problems, session_id=state.trace_id)
        unavailable = [self.theme.unavailable(result) for result in state.results if not result.ok]
        return {"points": _unique_ids([*points, *unavailable]), "drafts": state.drafts + 1}

    def _verify(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        results = {result.id: result for result in state.results}
        sources = {source.id: source for rule in state.rules for source in rule.sources}
        points = []
        for point in state.points:
            if point.status == "unavailable":
                points.append(point)
                continue
            problems = check_point(point, results, sources, state.subject) + self.theme.check(point)
            points.append(
                point.model_copy(update={"problems": problems, "status": "unverified" if problems else "verified"})
            )
        failed = any(point.status == "unverified" for point in points)
        return {"points": points, "next": "draft" if failed and state.drafts < self.limits.drafts else "review"}

    def _review(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        answer = interrupt({"kind": "review", "points": [point.model_dump() for point in state.points]})
        try:
            decisions = TypeAdapter(list[Decision]).validate_python(answer)
        except ValidationError:
            return {"next": "review"}
        return {"decisions": decisions}

    def _apply(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        by_point = {decision.point: decision for decision in state.decisions}
        missing = [point.id for point in state.points if point.id not in by_point]
        invalid = [d.point for d in state.decisions if d.action == "correct" and not (d.text or "").strip()]
        if missing or invalid:  # every point is decided, and a correction has its text
            return {"next": "review"}
        points = []
        for point in state.points:
            decision = by_point[point.id]
            if decision.action == "approve":
                points.append(point)
            elif decision.action == "correct":
                points.append(point.model_copy(update={"text": decision.text, "status": "corrected"}))
        return {"points": points}

    def _publish(self, state: AgentState, thread_id: str) -> dict[str, Any]:
        deliverable = self.theme.render(state.subject, state.points, state.rules)
        published = state.model_copy(update={"deliverable": deliverable, "status": "published"})
        for reason in [decision.reason for decision in state.decisions if decision.action != "approve"]:
            self.tracer.score("review.reason", reason or "none")
        self.tracer.score("review.approved", sum(d.action == "approve" for d in state.decisions))
        if self._on_publish is not None:
            self._on_publish(thread_id, published)
        return {"deliverable": deliverable, "status": "published"}


def _route(state: AgentState) -> str:
    return END if state.status == "stopped" else (state.next or END)


def _unique_ids(points: Sequence[Point]) -> list[Point]:
    seen: set[str] = set()
    unique = []
    for number, point in enumerate(points, start=1):
        point_id = point.id if point.id and point.id not in seen else f"P{number}"
        seen.add(point_id)
        unique.append(point.model_copy(update={"id": point_id}))
    return unique


def _brief(state: AgentState) -> dict[str, Any]:
    return {"request": state.request, "subject": state.subject, "spent": state.spent.model_dump()}


def _plain(value: Any) -> Any:
    """A node's update as JSON-ready data, for its span."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value
