"""Questions on a published deliverable (LAB-205): a direct answer, checked by code, with no person in between.

    scope -> pick -> run analyses -> [rule] -> reply -> check -> [reply -> check] -> answered | withheld

The context is the deliverable's: its subject, the analyses it ran and their outputs, the rules it found, and the
questions asked before. The theme fills each step (`ChatTheme`), and code decides the rest:

- **Scope is code.** A question about another subject (another race, for F1) is refused before any model call, with
  where to ask it instead.
- **A closed catalog.** The model may ask for more analyses of the subject's own catalog, a few at most, never
  another subject's; a question on the rules goes to the retrieval pipeline, as an event of the deliverable does.
- **Every number is checked**, by `check_point` as in a deliverable. A reply that fails is written again once with
  the problems found; one that still fails is withheld, and says why: an answer shown has no unbacked number.
- **Limits per question**: model calls and tokens, counted by `usage_scope`; over a limit, the question stops.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.agent.graph import check_point
from core.agent.state import AgentState, Analysis, Event, Point, Result, Rule, Spent
from core.gateway import Usage, usage_scope
from core.tools import ToolError
from core.tracing import Tracer


class ChatLimits(BaseSettings):
    """Read from the environment with the `AGENT_CHAT_` prefix: what one question may use."""

    model_config = SettingsConfigDict(env_prefix="AGENT_CHAT_", env_file=".env", extra="ignore")

    max_llm_calls: int = 12  # the retrieval pipeline's included
    max_tokens: int = 80_000
    max_analyses: int = 3  # run for the question, on top of the deliverable's
    replies: int = 2  # the first reply and one more after a failed check


class Pick(BaseModel):
    """What a question needs beyond the deliverable: analyses of the catalog, a question on the rules."""

    analyses: list[str] = Field(default_factory=list)
    rule_question: str | None = None


class Exchange(BaseModel):
    """A question asked before and its answer, for a follow-up ("et sous la voiture de sécurité ?")."""

    question: str
    answer: str


class ChatTheme(Protocol):
    """What a theme gives the questions. `pick`, `rule` and `reply` may call a model, and must validate what it
    returns; `scope`, `candidates`, `run` and `check` are code."""

    name: str

    def scope(self, subject: Mapping[str, Any], question: str) -> str | None:
        """Why the question is outside the subject, and where to ask it; None when it is the subject's."""
        ...

    def candidates(self, subject: Mapping[str, Any]) -> list[Analysis]: ...

    def run(self, analysis: Analysis) -> dict[str, Any]: ...

    def pick(
        self,
        question: str,
        subject: Mapping[str, Any],
        candidates: Sequence[Analysis],
        history: Sequence[Exchange],
        *,
        session_id: str | None,
    ) -> Pick: ...

    def rule(self, event: Event, *, session_id: str | None) -> Rule: ...

    def reply(
        self,
        question: str,
        subject: Mapping[str, Any],
        results: Sequence[Result],
        rules: Sequence[Rule],
        history: Sequence[Exchange],
        problems: Mapping[str, Sequence[str]],
        *,
        session_id: str | None,
    ) -> list[Point]:
        """The answer, in points citing their analyses and sources; `problems` are those found in the last reply."""
        ...

    def check(self, point: Point) -> list[str]: ...


class Reply(BaseModel):
    question: str
    status: Literal["answered", "withheld", "refused", "stopped"]
    points: list[Point] = Field(default_factory=list, description="The answer; empty unless answered")
    reason: str | None = Field(None, description="Why it is refused, withheld or stopped")
    results: list[Result] = Field(default_factory=list, description="The analyses run for this question")
    rules: list[Rule] = Field(default_factory=list, description="The rules found for this question")
    spent: Spent = Field(default_factory=Spent)


class Chat:
    def __init__(self, theme: ChatTheme, *, tracer: Tracer, limits: ChatLimits | None = None) -> None:
        self.theme = theme
        self.tracer = tracer
        self.limits = limits or ChatLimits()

    def ask(self, question: str, *, state: AgentState, history: Sequence[Exchange] = ()) -> Reply:
        """Answer a question on a deliverable, whose state (subject, results, rules) is the context."""
        if refusal := self.theme.scope(state.subject, question):
            return Reply(question=question, status="refused", reason=refusal)
        with (
            self.tracer.trace(f"{self.theme.name}.chat", {"question": question}) as session,
            usage_scope() as usage,
        ):
            reply = self._answer(question, state, history, usage, session)
            reply.spent = Spent(steps=1, llm_calls=usage.calls, tokens=usage.tokens)
            self.tracer.output({"status": reply.status, "reason": reply.reason, "spent": reply.spent.model_dump()})
        self.tracer.flush()
        return reply

    def _answer(
        self, question: str, state: AgentState, history: Sequence[Exchange], usage: Usage, session: str | None
    ) -> Reply:
        done = {result.id for result in state.results if result.ok}
        catalog = {analysis.id: analysis for analysis in self.theme.candidates(state.subject)}
        pick = self.theme.pick(question, state.subject, list(catalog.values()), history, session_id=session)
        wanted = [id_ for id_ in dict.fromkeys(pick.analyses) if id_ in catalog and id_ not in done]
        new = [self._run(catalog[id_]) for id_ in wanted[: self.limits.max_analyses]]
        rules: list[Rule] = []
        if pick.rule_question and not self._over(usage):
            event = Event(id="Q", kind="question", summary=question, question=pick.rule_question)
            rules.append(self.theme.rule(event, session_id=session))
        reply = Reply(question=question, status="answered", results=new, rules=rules)
        results = [result for result in [*state.results, *new] if result.ok]
        every_rule = [*state.rules, *rules]
        by_id = {result.id: result for result in [*state.results, *new]}
        sources = {source.id: source for rule in every_rule for source in rule.sources}
        problems: dict[str, list[str]] = {}
        for _ in range(self.limits.replies):
            if reason := self._over(usage):
                return reply.model_copy(update={"status": "stopped", "reason": reason})
            points = self.theme.reply(
                question, state.subject, results, every_rule, history, problems, session_id=session
            )
            checked = [
                point.model_copy(update={"problems": found, "status": "unverified" if found else "verified"})
                for point in points
                for found in [check_point(point, by_id, sources, state.subject) + self.theme.check(point)]
            ]
            problems = {point.text: point.problems for point in checked if point.problems}
            if not problems:
                return reply.model_copy(update={"points": checked})
        found = "; ".join(f"« {text} » : {', '.join(why)}" for text, why in problems.items())
        return reply.model_copy(update={"status": "withheld", "reason": found})

    def _run(self, analysis: Analysis) -> Result:
        result = Result(id=analysis.id, tool=analysis.tool, label=analysis.label, arguments=analysis.arguments)
        try:
            result.output = self.theme.run(analysis)
        except ToolError as error:
            result.error = str(error)
        except Exception as error:  # a bug of a tool is no number either
            result.error = f"{type(error).__name__}: {error}"
        return result

    def _over(self, usage: Usage) -> str | None:
        if usage.calls >= self.limits.max_llm_calls:
            return f"{usage.calls} model calls, the limit"
        if usage.tokens >= self.limits.max_tokens:
            return f"{usage.tokens} tokens, over the limit of {self.limits.max_tokens}"
        return None
