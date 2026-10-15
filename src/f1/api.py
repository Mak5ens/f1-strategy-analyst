"""HTTP API of the app: the debrief agent's requests, their three stops, and the published debriefs (LAB-152).

The front in `web/` calls it through a client generated from this app's OpenAPI document, committed as
`web/openapi.json` (`just web-gen-client`): `tests/unit/test_api.py` fails while the two differ.

    uv run python -m f1.api > web/openapi.json

A request runs inside the HTTP call that starts or answers it, until its next stop: a few seconds to the plan, up to
half a minute from the plan to the review when rules are needed.
"""

import json
import threading
import uuid
from collections.abc import Mapping
from contextlib import ExitStack
from datetime import datetime
from importlib.metadata import version
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.agent import Agent, Analysis, Clarification, Decision, Point, Run
from core.agent.store import RequestStore
from f1.display import grand_prix_fr, team_colour

# The version of the API contract, not the app's: release-please bumps the app's on every release, and the OpenAPI
# document, and the front's generated client, would change with it.
app = FastAPI(title="F1 Strategy Analyst", version="0.1.0")

Status = Literal["running", "waiting", "stopped", "published"]
Stop = Literal["clarification", "plan", "review"]


class Response(BaseModel):
    """What the API returns: every field always present, its default included, so the generated client needs no
    `?? []`."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Health(BaseModel):
    status: str


class Info(BaseModel):
    name: str
    version: str


class Driver(Response):
    code: str
    name: str
    team: str | None = None
    colour: str | None = Field(None, description="The team's colour, #rrggbb, when known")


class Subject(Response):
    """What a request is about, as far as the agent resolved it: nothing yet while it asks which race."""

    season: int | None = None
    round: int | None = None
    grand_prix: str | None = Field(None, description="In French")
    kind: Literal["race", "team", "driver"] | None = None
    teams: list[str] = Field(default_factory=list)
    focus: list[Driver] = Field(default_factory=list, description="The drivers the debrief follows")
    colour: str | None = Field(None, description="The colour of the team followed, or of the first driver's team")


class DebriefSummary(Response):
    id: str
    request: str
    status: Status
    waiting: Stop | None = Field(None, description="The stop the request waits at, if it waits for a person")
    subject: Subject
    created_at: datetime
    updated_at: datetime


class Debrief(Response):
    """A request and everything a person needs at its stop."""

    id: str
    request: str
    status: Status
    waiting: Stop | None = None
    subject: Subject
    clarification: Clarification | None = Field(None, description="The open question, when waiting for it")
    plan: list[Analysis] = Field(default_factory=list)
    points: list[Point] = Field(default_factory=list)
    deliverable: str | None = Field(None, description="The published debrief, in Markdown")
    stop_reason: str | None = None


class NewDebrief(BaseModel):
    request: str = Field(
        min_length=3, max_length=500, examples=["Débrief stratégique du GP d'Italie 2025 pour Ferrari"]
    )


class ClarificationAnswer(BaseModel):
    option: str = Field(description="The label of the option chosen")


class PlanAnswer(BaseModel):
    analyses: list[str] = Field(description="The ids of the analyses to run")


class ReviewAnswer(BaseModel):
    decisions: list[Decision]


# The agent and the request store, opened on first use and kept for the life of the process.

_resources = ExitStack()
_lock = threading.Lock()
_agent: Agent | None = None
_requests: RequestStore | None = None


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


AgentDep = Annotated[Agent, Depends(get_agent)]
RequestsDep = Annotated[RequestStore, Depends(get_requests)]


@app.get("/healthz")
def healthz() -> Health:
    """Liveness probe: the process answers. It does not check the gateway or the databases."""
    return Health(status="ok")


@app.get("/info")
def info() -> Info:
    """The service and the version of the app it runs."""
    return Info(name="f1-strategy-analyst", version=version("f1-strategy-analyst"))


@app.get("/debriefs")
def list_debriefs(
    requests: RequestsDep,
    status: Annotated[Status | None, Query(description="Only the requests of this status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DebriefSummary]:
    """The requests, the latest first: those waiting for a person with `status=waiting`."""
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
        for row in requests.list(status=status, limit=limit)
    ]


@app.post("/debriefs", status_code=201)
def start_debrief(body: NewDebrief, agent: AgentDep) -> Debrief:
    """Start a debrief: the agent runs until its first stop, usually the plan, or a clarification."""
    return debrief(agent.start(body.request, thread_id=str(uuid.uuid4())))


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


@app.post("/debriefs/{debrief_id}/review")
def answer_review(debrief_id: str, body: ReviewAnswer, agent: AgentDep) -> Debrief:
    """One decision per point: approve, correct (with the text) or reject, with a reason unless approved."""
    _waiting(agent, debrief_id, "review")
    return debrief(agent.resume(debrief_id, [decision.model_dump() for decision in body.decisions]))


def _run(agent: Agent, debrief_id: str) -> Run:
    try:
        return agent.get(debrief_id)
    except KeyError:
        raise HTTPException(404, f"no debrief {debrief_id}") from None


def _waiting(agent: Agent, debrief_id: str, stop: Stop) -> None:
    run = _run(agent, debrief_id)
    if run.waiting is None or run.waiting.kind != stop:
        raise HTTPException(409, f"debrief {debrief_id} is not waiting for its {stop} ({run.status})")


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
        points=state.points,
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
    )


def openapi_document() -> str:
    """The OpenAPI document as committed in `web/openapi.json`: indented, keys in the app's order, a final newline."""
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(openapi_document(), end="")
