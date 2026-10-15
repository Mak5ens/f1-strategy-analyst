"""The state of a controlled agent: everything a request went through, typed, saved at every step.

The checkpointer saves this state after each node, so a request waiting for a person (a clarification, the plan, the
review) survives a restart. Nothing here is specific to a theme: what the request is about (`subject`) and what the
analyses compute (`Result.output`) are the theme's data.
"""

from typing import Any, Literal

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel, Field


class Option(BaseModel):
    """One answer proposed to a person: what is shown, and what it sets in the subject."""

    label: str
    value: dict[str, Any] = Field(default_factory=dict)


class Clarification(BaseModel):
    """What the agent will not guess: the request is ambiguous or names something unknown."""

    field: str  # what is asked, e.g. "grand_prix"
    question: str
    options: list[Option]
    answer: str | None = None  # the label of the option chosen


class Analysis(BaseModel):
    """One analysis of the closed catalog: a tool and its arguments, decided by code."""

    id: str
    tool: str
    arguments: dict[str, Any]
    label: str  # what it is, for the person who validates the plan
    selected: bool = True


class Result(BaseModel):
    """What an analysis computed, or why it could not: a failed analysis gives no number, ever."""

    id: str
    tool: str
    label: str
    arguments: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.output is not None


class Event(BaseModel):
    """Something of the data that a rule explains (a penalty, a neutralization), and the question asked about it."""

    id: str
    kind: str
    summary: str
    question: str


class RuleSource(BaseModel):
    id: str  # unique in the request: "<event>:S1"
    label: str
    text: str


class Rule(BaseModel):
    """What the retrieval pipeline found on an event's question: claims, each citing its sources."""

    event: str
    question: str
    answered: bool
    claims: list[str] = Field(default_factory=list)
    sources: list[RuleSource] = Field(default_factory=list)


PointStatus = Literal["draft", "verified", "unverified", "unavailable", "corrected"]


class Point(BaseModel):
    """One point of the deliverable: a text, the results its numbers come from, the sources it cites."""

    id: str
    text: str
    facts: list[str] = Field(default_factory=list, description="Ids of the analyses whose numbers the text uses")
    sources: list[str] = Field(default_factory=list, description="Ids of the rule sources the text cites")
    status: PointStatus = "draft"
    problems: list[str] = Field(default_factory=list)


RejectReason = Literal["wrong_number", "wrong_source", "off_topic", "wording", "other"]


class Decision(BaseModel):
    """A person's decision on a point. A correction replaces the text; a rejection drops the point. Both say why."""

    point: str
    action: Literal["approve", "correct", "reject"]
    text: str | None = None
    reason: RejectReason | None = None


class Spent(BaseModel):
    """What the request has used so far, against the agent's limits."""

    steps: int = 0
    llm_calls: int = 0
    tokens: int = 0


Status = Literal["running", "waiting", "stopped", "published"]


class AgentState(BaseModel):
    request: str
    trace_id: str | None = None
    subject: dict[str, Any] = Field(default_factory=dict)
    clarification: Clarification | None = None  # the open question, if any
    clarifications: list[Clarification] = Field(default_factory=list)  # the answered ones
    plan: list[Analysis] = Field(default_factory=list)
    plan_approved: bool = False
    results: list[Result] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    points: list[Point] = Field(default_factory=list)
    drafts: int = 0
    decisions: list[Decision] = Field(default_factory=list)
    deliverable: str | None = None
    spent: Spent = Field(default_factory=Spent)
    status: Status = "running"
    stop_reason: str | None = None
    next: str | None = None  # the routing decision of the last node, read by the edges


def serializer() -> JsonPlusSerializer:
    """LangGraph's serializer, told that the state's models may be read back from a checkpoint (and nothing else)."""
    models = [Option, Clarification, Analysis, Result, Event, RuleSource, Rule, Point, Decision, Spent, AgentState]
    return JsonPlusSerializer(allowed_msgpack_modules=[(model.__module__, model.__name__) for model in models])
