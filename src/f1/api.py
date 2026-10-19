"""HTTP API of the app: the races of the lake (LAB-202), the debrief agent's requests, their three stops, and the
published debriefs (LAB-152).

The front in `web/` calls it through a client generated from this app's OpenAPI document, committed as
`web/openapi.json` (`just web-gen-client`): `tests/unit/test_api.py` fails while the two differ.

    uv run python -m f1.api > web/openapi.json

The races' pages are read from the lake, without a model. A request runs inside the HTTP call that starts or
answers it, until its next stop: a few seconds to the plan, up to half a minute from the plan to the review when
rules are needed.
"""

import functools
import json
import threading
import uuid
from collections.abc import Mapping
from contextlib import ExitStack
from datetime import datetime
from importlib.metadata import version
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from core.agent import Agent, Analysis, Clarification, Decision, Point, Run
from core.agent.chat import Chat, Exchange, Reply
from core.agent.state import AgentState, RejectReason
from core.agent.store import RequestStore
from f1.display import Driver, Response, grand_prix_fr, team_colour
from f1.grand_prix import GrandPrix, Race, RaceLaps, RaceSummary
from f1.questions import FreeAnswer, FreeQuestions, FreeQuestionStore
from f1.router import Route, Router

# The version of the API contract, not the app's: release-please bumps the app's on every release, and the OpenAPI
# document, and the front's generated client, would change with it.
app = FastAPI(title="F1 Strategy Analyst", version="0.1.0")

Status = Literal["running", "waiting", "stopped", "published"]
Stop = Literal["clarification", "plan", "review"]


class Health(BaseModel):
    status: str


class Info(BaseModel):
    name: str
    version: str


class Subject(Response):
    """What a request is about, as far as the agent resolved it: nothing yet while it asks which race."""

    season: int | None = None
    round: int | None = None
    grand_prix: str | None = Field(None, description="In French")
    kind: Literal["race", "team", "driver"] | None = None
    teams: list[str] = Field(default_factory=list)
    focus: list[Driver] = Field(default_factory=list, description="The drivers the debrief follows")
    colour: str | None = Field(None, description="The colour of the team followed, or of the first driver's team")
    question: bool = Field(False, description="A precise question on the race: its request is its title")
    moments: bool = Field(False, description="The moments that made the race, found and ranked by code (LAB-204)")
    prepared: Literal["team", "moments", "driver"] | None = Field(
        None, description="Prepared after the race by `just debriefs-prepare`, not asked by an analyst"
    )


class DebriefSummary(Response):
    id: str
    request: str
    status: Status
    waiting: Stop | None = Field(None, description="The stop the request waits at, if it waits for a person")
    subject: Subject
    created_at: datetime
    updated_at: datetime


class ShownPoint(Response, Point):
    """A point of the debrief, its lists always present."""


class Fact(Response):
    """An analysis the agent ran: the points cite it for their numbers."""

    id: str
    label: str
    ok: bool
    error: str | None = Field(None, description="Why it gave no number")


class Source(Response):
    """A passage of the FIA documents the points may cite."""

    id: str
    label: str
    text: str


class Debrief(Response):
    """A request and everything a person needs at its stop."""

    id: str
    request: str
    status: Status
    waiting: Stop | None = None
    subject: Subject
    clarification: Clarification | None = Field(None, description="The open question, when waiting for it")
    plan: list[Analysis] = Field(default_factory=list)
    points: list[ShownPoint] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list, description="The analyses run, which `Point.facts` cite")
    sources: list[Source] = Field(default_factory=list, description="The rule passages, which `Point.sources` cite")
    decisions: list[Decision] = Field(default_factory=list, description="The review's, once made")
    deliverable: str | None = Field(None, description="The published debrief, in Markdown")
    stop_reason: str | None = None


class QuestionReply(Response):
    """A question asked on a published debrief, and its reply: shown only when every number is backed."""

    id: int
    question: str
    status: Literal["answered", "withheld", "refused", "stopped"]
    points: list[ShownPoint] = Field(default_factory=list, description="The answer; empty unless answered")
    facts: list[Fact] = Field(default_factory=list, description="The analyses its points cite")
    sources: list[Source] = Field(default_factory=list, description="The rule passages its points cite")
    reason: str | None = Field(None, description="Why it is refused, withheld or stopped")
    asked_at: datetime


class NewQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=500, examples=["Détaille le cycle d'arrêts de Leclerc"])


class JournalEntry(Response):
    """A decision of a review, kept with the agent's text it judged."""

    id: int
    debrief: str
    request: str
    subject: Subject
    point: str
    action: Literal["approve", "correct", "reject"]
    reason: RejectReason | None = None
    text_before: str = Field(description="The agent's text")
    text_after: str | None = Field(None, description="The corrected text")
    point_status: str | None = Field(None, description="What the agent's check said of the point")
    decided_by: str
    decided_at: datetime


class NewDebrief(BaseModel):
    request: str = Field(
        min_length=3, max_length=500, examples=["Débrief stratégique du GP d'Italie 2025 pour Ferrari"]
    )
    season: int | None = Field(None, ge=2018, le=2100, description="The race chosen, with `round`: never asked for")
    round: int | None = Field(None, ge=1, le=30)
    question: bool = Field(False, description="A precise question on the race: the debrief answers it first")

    @model_validator(mode="after")
    def _race_whole(self) -> "NewDebrief":
        if (self.season is None) != (self.round is None):
            raise ValueError("a race is a season and a round")
        return self

    def given(self) -> dict[str, Any]:
        """What the person chose beside the request, as the agent's subject fields."""
        given: dict[str, Any] = {"question": True} if self.question else {}
        if self.season is not None and self.round is not None:
            given |= {"season": self.season, "round": self.round}
        return given


class ClarificationAnswer(BaseModel):
    option: str = Field(description="The label of the option chosen")


class PlanAnswer(BaseModel):
    analyses: list[str] = Field(description="The ids of the analyses to run")


class ReviewAnswer(BaseModel):
    decisions: list[Decision]


class NewFreeQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=500, examples=["Peut-on changer de pneus sous drapeau rouge ?"])
    route: Route | None = Field(None, description="The path the analyst chose, when asked")
    season: int | None = Field(None, ge=2018, le=2100, description="The race the analyst chose, with `round`")
    round: int | None = Field(None, ge=1, le=30)

    @model_validator(mode="after")
    def _race_whole(self) -> "NewFreeQuestion":
        if (self.season is None) != (self.round is None):
            raise ValueError("a race is a season and a round")
        return self


# The agent and the request store, opened on first use and kept for the life of the process.

_resources = ExitStack()
_lock = threading.Lock()
_agent: Agent | None = None
_requests: RequestStore | None = None
_grand_prix: GrandPrix | None = None
_chat: Chat | None = None
_free: FreeQuestions | None = None
_free_store: FreeQuestionStore | None = None


def get_agent() -> Agent:
    global _agent
    with _lock:
        if _agent is None:
            from f1.agent import debrief_agent

            _agent = _resources.enter_context(debrief_agent())
    return _agent


def get_requests() -> RequestStore:
    global _requests
    with _lock:
        if _requests is None:
            _requests = RequestStore()
    return _requests


def get_grand_prix() -> GrandPrix:
    global _grand_prix
    with _lock:
        if _grand_prix is None:
            from f1.data import connect

            _grand_prix = GrandPrix(connect())
    return _grand_prix


def get_chat() -> Chat:
    global _chat
    with _lock:
        if _chat is None:
            from f1.agent import debrief_chat

            _chat = debrief_chat()
    return _chat


def get_free_questions(grand_prix: Annotated[GrandPrix, Depends(get_grand_prix)]) -> FreeQuestions:
    """The router knows the drivers and teams of the lake; the rules and the chat open on the first question that
    needs them."""
    global _free
    with _lock:
        if _free is None:
            from f1.rag import rag_pipeline

            router = Router(*grand_prix.people())
            _free = FreeQuestions(router, grand_prix, rules=functools.cache(rag_pipeline), chat=get_chat)
    return _free


def get_free_store() -> FreeQuestionStore:
    global _free_store
    with _lock:
        if _free_store is None:
            _free_store = FreeQuestionStore()
    return _free_store


AgentDep = Annotated[Agent, Depends(get_agent)]
ChatDep = Annotated[Chat, Depends(get_chat)]
RequestsDep = Annotated[RequestStore, Depends(get_requests)]
GrandPrixDep = Annotated[GrandPrix, Depends(get_grand_prix)]
FreeQuestionsDep = Annotated[FreeQuestions, Depends(get_free_questions)]
FreeStoreDep = Annotated[FreeQuestionStore, Depends(get_free_store)]


@app.get("/healthz")
def healthz() -> Health:
    """Liveness probe: the process answers. It does not check the gateway or the databases."""
    return Health(status="ok")


@app.get("/info")
def info() -> Info:
    """The service and the version of the app it runs."""
    return Info(name="f1-strategy-analyst", version=version("f1-strategy-analyst"))


@app.get("/seasons")
def list_seasons(grand_prix: GrandPrixDep) -> list[int]:
    """The seasons with races in the data, the latest first."""
    return grand_prix.seasons()


@app.get("/races")
def list_races(
    grand_prix: GrandPrixDep, season: Annotated[int | None, Query(description="The latest season if omitted")] = None
) -> list[RaceSummary]:
    """The calendar of a season, as far as the data goes: every round, with its winner once raced."""
    seasons = grand_prix.seasons()
    return grand_prix.calendar(season or seasons[0]) if seasons else []


@app.get("/races/featured")
def featured_races(grand_prix: GrandPrixDep, requests: RequestsDep) -> list[RaceSummary]:
    """The races to put forward: the last one raced, then the latest with a debrief, then the rounds before."""
    debriefed = [
        (row["subject"]["season"], row["subject"]["round"])
        for row in requests.list(limit=200)
        if row["subject"].get("season") and row["subject"].get("round")
    ]
    return grand_prix.featured(debriefed)


@app.get("/races/{season}/{round_number}")
def get_race(season: int, round_number: int, grand_prix: GrandPrixDep) -> Race:
    """What a Grand Prix's page shows: result, grid, best laps, strategies, stops, neutralizations, penalties,
    standings after the round, weather. Read from the lake: no model is called."""
    race = grand_prix.race(season, round_number)
    if race is None:
        raise HTTPException(404, f"no data for round {round_number} of {season}")
    return race


@app.get("/races/{season}/{round_number}/laps")
def get_race_laps(season: int, round_number: int, grand_prix: GrandPrixDep) -> RaceLaps:
    """A race lap by lap for its charts (LAB-189): each driver's position, gap to the leader at the line, lap time
    and tyres, with the neutralizations. Read from the lake: no model is called."""
    laps = grand_prix.laps(season, round_number)
    if laps is None:
        raise HTTPException(404, f"no laps for round {round_number} of {season}: not raced, or not in the lake")
    return laps


@app.get("/debriefs")
def list_debriefs(
    requests: RequestsDep,
    status: Annotated[Status | None, Query(description="Only the requests of this status")] = None,
    season: Annotated[int | None, Query(description="Only the requests on a race of this season")] = None,
    round_number: Annotated[int | None, Query(alias="round", description="Only those on this round")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DebriefSummary]:
    """The requests, the latest first: those waiting for a person with `status=waiting`, those on a race with
    `season` and `round`."""
    race = {key: value for key, value in (("season", season), ("round", round_number)) if value is not None}
    return [
        DebriefSummary(
            id=row["thread_id"],
            request=row["request"],
            status=row["status"],
            waiting=row["waiting"],
            subject=subject(row["subject"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in requests.list(status=status, subject=race, limit=limit)
    ]


@app.post("/questions", status_code=201)
def ask_free_question(
    body: NewFreeQuestion, questions: FreeQuestionsDep, store: FreeStoreDep, agent: AgentDep
) -> FreeAnswer:
    """A free question of the home page (LAB-206), sent by code down its path: the rules (the retrieval pipeline),
    the data of the race it names (a direct answer, every number checked), or a debrief (the agent, started here:
    `debrief` is its request). When the path or the race is not clear, `choices` says what the analyst may pick,
    sent back with the question."""
    answer = questions.ask(body.question, route=body.route, season=body.season, round_number=body.round)
    if answer.status == "debrief":
        run = agent.start(body.question, thread_id=str(uuid.uuid4()))
        answer = answer.model_copy(update={"debrief": run.thread_id})
    return store.save(answer)


@app.get("/questions")
def list_free_questions(store: FreeStoreDep, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> list[FreeAnswer]:
    """The latest free questions first, with their answers."""
    return store.latest(limit)


@app.get("/questions/{question_id}")
def get_free_question(question_id: int, store: FreeStoreDep) -> FreeAnswer:
    if (answer := store.get(question_id)) is None:
        raise HTTPException(404, f"no question {question_id}")
    return answer


@app.post("/debriefs", status_code=201)
def start_debrief(body: NewDebrief, agent: AgentDep) -> Debrief:
    """Start a debrief: the agent runs until its first stop, usually the plan, or a clarification. A race given with
    `season` and `round` is never asked for; `question` asks for an answer first (LAB-203)."""
    return debrief(agent.start(body.request, thread_id=str(uuid.uuid4()), given=body.given()))


@app.get("/debriefs/{debrief_id}")
def get_debrief(debrief_id: str, agent: AgentDep) -> Debrief:
    return debrief(_run(agent, debrief_id))


@app.post("/debriefs/{debrief_id}/clarification")
def answer_clarification(debrief_id: str, body: ClarificationAnswer, agent: AgentDep) -> Debrief:
    """Choose one of the options of the open question."""
    _waiting(agent, debrief_id, "clarification")
    return debrief(agent.resume(debrief_id, body.option))


@app.post("/debriefs/{debrief_id}/plan")
def answer_plan(debrief_id: str, body: PlanAnswer, agent: AgentDep) -> Debrief:
    """Validate the plan: the analyses kept run, then the agent drafts and checks the points, up to the review."""
    _waiting(agent, debrief_id, "plan")
    return debrief(agent.resume(debrief_id, body.analyses))


@app.get("/debriefs/{debrief_id}/questions")
def list_questions(debrief_id: str, agent: AgentDep, requests: RequestsDep) -> list[QuestionReply]:
    """The questions asked on a debrief, the first first."""
    state = _run(agent, debrief_id).state
    return [question_reply(row, state) for row in requests.replies(debrief_id)]


@app.post("/debriefs/{debrief_id}/questions", status_code=201)
def ask_question(
    debrief_id: str, body: NewQuestion, agent: AgentDep, chat: ChatDep, requests: RequestsDep
) -> QuestionReply:
    """A question on a published debrief, answered directly: its context is the debrief's race, analyses and rules.
    A reply with a number no analysis backs is withheld; a question on another race is refused."""
    run = _run(agent, debrief_id)
    if run.status != "published":
        raise HTTPException(409, f"debrief {debrief_id} is not published ({run.status})")
    history = [
        Exchange(question=row["question"], answer=" ".join(point["text"] for point in row["reply"]["points"]))
        for row in requests.replies(debrief_id)
        if row["status"] == "answered"
    ]
    reply = chat.ask(body.question, state=run.state, history=history)
    return question_reply(requests.save_reply(debrief_id, reply), run.state)


def question_reply(row: Mapping[str, Any], state: AgentState) -> QuestionReply:
    reply = Reply.model_validate(row["reply"])
    results = {result.id: result for result in [*state.results, *reply.results]}
    passages = {source.id: source for rule in [*state.rules, *reply.rules] for source in rule.sources}
    cited = [id_ for point in reply.points for id_ in point.facts]
    quoted = [id_ for point in reply.points for id_ in point.sources]
    return QuestionReply(
        id=row["id"],
        question=reply.question,
        status=reply.status,
        points=[ShownPoint.model_validate(point.model_dump()) for point in reply.points],
        facts=[
            Fact(id=r.id, label=r.label, ok=r.ok, error=r.error)
            for id_ in dict.fromkeys(cited)
            if (r := results.get(id_))
        ],
        sources=[
            Source(id=p.id, label=p.label, text=p.text) for id_ in dict.fromkeys(quoted) if (p := passages.get(id_))
        ],
        reason=reply.reason,
        asked_at=row["asked_at"],
    )


# Who decides, until the site has accounts (milestone 6): its owner, the analyst.
REVIEWER = "analyste"


@app.post("/debriefs/{debrief_id}/review")
def answer_review(debrief_id: str, body: ReviewAnswer, agent: AgentDep, requests: RequestsDep) -> Debrief:
    """One decision per point: approve, correct (with the text) or reject, with a reason unless approved. Each
    decision is logged with the agent's text, once the agent accepts the review."""
    points = _waiting(agent, debrief_id, "review").state.points
    run = agent.resume(debrief_id, [decision.model_dump() for decision in body.decisions])
    if run.waiting is None or run.waiting.kind != "review":
        requests.log_decisions(debrief_id, points, body.decisions, by=REVIEWER)
    return debrief(run)


@app.get("/decisions")
def list_decisions(
    requests: RequestsDep,
    debrief_id: Annotated[str | None, Query(alias="debrief", description="Only those of this debrief")] = None,
    action: Annotated[list[Literal["approve", "correct", "reject"]] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[JournalEntry]:
    """The journal of the reviews, the latest first."""
    return [
        JournalEntry(
            id=row["id"],
            debrief=row["thread_id"],
            request=row["request"],
            subject=subject(row["subject"]),
            point=row["point"],
            action=row["action"],
            reason=row["reason"],
            text_before=row["text_before"],
            text_after=row["text_after"],
            point_status=row["point_status"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
        )
        for row in requests.decisions(thread_id=debrief_id, actions=action, limit=limit)
    ]


def _run(agent: Agent, debrief_id: str) -> Run:
    try:
        return agent.get(debrief_id)
    except KeyError:
        raise HTTPException(404, f"no debrief {debrief_id}") from None


def _waiting(agent: Agent, debrief_id: str, stop: Stop) -> Run:
    run = _run(agent, debrief_id)
    if run.waiting is None or run.waiting.kind != stop:
        raise HTTPException(409, f"debrief {debrief_id} is not waiting for its {stop} ({run.status})")
    return run


def debrief(run: Run) -> Debrief:
    state = run.state
    waiting = run.waiting.kind if run.waiting else None
    return Debrief(
        id=run.thread_id,
        request=state.request,
        status=run.status,
        waiting=waiting,
        subject=subject(state.subject),
        clarification=state.clarification if waiting == "clarification" else None,
        plan=state.plan,
        points=[ShownPoint.model_validate(point.model_dump()) for point in state.points],
        facts=[Fact(id=r.id, label=r.label, ok=r.ok, error=r.error) for r in state.results],
        sources=[Source(id=src.id, label=src.label, text=src.text) for rule in state.rules for src in rule.sources],
        decisions=state.decisions,
        deliverable=state.deliverable,
        stop_reason=state.stop_reason,
    )


def subject(raw: Mapping[str, Any]) -> Subject:
    """The agent's subject (`f1.agent.theme`) as the front shows it: French names, drivers with their team colour."""
    entry = {driver["code"]: driver for driver in raw.get("entry", [])}
    focus = [
        Driver(code=code, name=entry[code]["name"], team=entry[code]["team"], colour=team_colour(entry[code]["team"]))
        for code in raw.get("focus", [])
        if code in entry
    ]
    teams = list(raw.get("teams", []))
    lead = teams[0] if teams else focus[0].team if raw.get("kind") == "driver" and focus else None
    return Subject(
        season=raw.get("season"),
        round=raw.get("round"),
        grand_prix=grand_prix_fr(raw["event"]) if raw.get("event") else None,
        kind=raw.get("kind"),
        teams=teams,
        focus=focus,
        colour=team_colour(lead),
        question=bool(raw.get("question")),
        moments=bool(raw.get("moments")),
        prepared=raw.get("prepared"),
    )


def openapi_document() -> str:
    """The OpenAPI document as committed in `web/openapi.json`: indented, keys in the app's order, a final newline."""
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(openapi_document(), end="")
