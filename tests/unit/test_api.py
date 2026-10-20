from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_agent import FakeTheme, agent
from test_auth import authenticator, token
from test_chat import FakeChatTheme

from core.agent import Agent, Decision, Point, Run
from core.agent.chat import Chat, ChatLimits, Reply
from core.auth import Authenticator, AuthSettings
from core.tracing import Tracer
from f1.api import (
    app,
    get_agent,
    get_authenticator,
    get_chat,
    get_free_questions,
    get_free_store,
    get_requests,
    openapi_document,
    subject,
)
from f1.questions import AnswerPoint, Cited, FreeAnswer
from f1.router import Route

OPENAPI = Path(__file__).parents[2] / "web" / "openapi.json"


class FakeRequests:
    """The request store, in memory."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.journal: list[dict[str, Any]] = []
        self.questions: list[dict[str, Any]] = []

    def record(self, run: Run) -> None:
        now = datetime.now(UTC)
        row = self.rows.setdefault(run.thread_id, {"thread_id": run.thread_id, "created_at": now})
        row.update(
            request=run.state.request,
            subject=run.state.subject,
            status=run.status,
            waiting=run.waiting.kind if run.waiting else None,
            updated_at=now,
        )

    def log_decisions(self, thread_id: str, points: Sequence[Point], decisions: Sequence[Decision], *, by: str) -> None:
        texts = {point.id: (point.text, point.status) for point in points}
        for decision in decisions:
            before, status = texts[decision.point]
            self.journal.insert(0, {
                "id": len(self.journal) + 1, "thread_id": thread_id, "point": decision.point,
                "action": decision.action, "reason": decision.reason, "text_before": before,
                "text_after": decision.text if decision.action == "correct" else None, "point_status": status,
                "decided_by": by, "decided_at": datetime.now(UTC), "request": self.rows[thread_id]["request"],
                "subject": self.rows[thread_id]["subject"],
            })  # fmt: skip

    def save_reply(self, thread_id: str, reply: Reply) -> dict[str, Any]:
        row = {"id": len(self.questions) + 1, "thread_id": thread_id, "question": reply.question,
               "status": reply.status, "reply": reply.model_dump(mode="json"),
               "asked_at": datetime.now(UTC)}  # fmt: skip
        self.questions.append(row)
        return row

    def replies(self, thread_id: str) -> list[dict[str, Any]]:
        return [row for row in self.questions if row["thread_id"] == thread_id]

    def decisions(
        self, *, thread_id: str | None = None, actions: Sequence[str] | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in self.journal
            if (thread_id is None or row["thread_id"] == thread_id) and (not actions or row["action"] in actions)
        ][:limit]

    def list(
        self, *, status: str | None = None, subject: dict[str, Any] | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows = [
            row
            for row in self.rows.values()
            if (status is None or row["status"] == status) and (subject or {}).items() <= row["subject"].items()
        ]
        return sorted(rows, key=lambda row: row["updated_at"], reverse=True)[:limit]


class FakeFreeQuestions:
    """The paths of the free question, scripted: the rules answer, a debrief is routed (LAB-206)."""

    def ask(
        self, question: str, *, route: Route | None = None, season: int | None = None, round_number: int | None = None
    ) -> FreeAnswer:
        if question.startswith("Débrief"):
            return FreeAnswer(question=question, route="debrief", status="debrief")
        source = Cited(id="S1", label="Règlement sportif F1 2025, article 57.3", url="https://www.fia.com/x")
        point = AnswerPoint(text="Oui, pendant la suspension.", sources=["S1"])
        return FreeAnswer(question=question, route="rules", status="answered", points=[point], sources=[source])


class FakeFreeStore:
    def __init__(self) -> None:
        self.rows: list[FreeAnswer] = []

    def save(self, answer: FreeAnswer) -> FreeAnswer:
        saved = answer.model_copy(update={"id": len(self.rows) + 1, "asked_at": datetime.now(UTC)})
        self.rows.append(saved)
        return saved

    def get(self, question_id: int) -> FreeAnswer | None:
        return next((row for row in self.rows if row.id == question_id), None)

    def latest(self, limit: int = 10) -> list[FreeAnswer]:
        return [row for row in reversed(self.rows) if row.status != "asked"][:limit]


ANSWERS = [
    [Point(id="A1", text="Leclerc a perdu 21.4 s au tour 23.", facts=["loss:LEC"])],
    [Point(id="A1", text="Leclerc a perdu 30 s.", facts=["loss:LEC"])],  # wrong, twice: withheld
    [Point(id="A1", text="Leclerc a perdu 30 s.", facts=["loss:LEC"])],
]


@pytest.fixture
def client() -> Iterator[TestClient]:
    requests = FakeRequests()
    bot: Agent = agent(FakeTheme())
    bot._on_run = requests.record
    app.dependency_overrides[get_agent] = lambda: bot
    app.dependency_overrides[get_requests] = lambda: requests
    chat = Chat(
        FakeChatTheme([list(answer) for answer in ANSWERS]), tracer=Tracer(None), limits=ChatLimits(_env_file=None)
    )
    app.dependency_overrides[get_chat] = lambda: chat
    free, store = FakeFreeQuestions(), FakeFreeStore()
    app.dependency_overrides[get_free_questions] = lambda: free
    app.dependency_overrides[get_free_store] = lambda: store
    # Open, as without an SSO: every caller is the local analyst. `signed` below checks the accounts.
    open_api = Authenticator(AuthSettings(_env_file=None))
    app.dependency_overrides[get_authenticator] = lambda: open_api
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def signed(client: TestClient) -> TestClient:
    """The same app behind the SSO: a request carries an account's token, or none."""
    checked = authenticator()
    app.dependency_overrides[get_authenticator] = lambda: checked
    return client


def as_analyst() -> dict[str, str]:
    return {"Authorization": f"Bearer {token()}"}


def as_reader() -> dict[str, str]:
    return {"Authorization": f"Bearer {token('a-reader')}"}


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_info_names_the_app_and_its_version() -> None:
    response = TestClient(app).get("/info")

    assert response.json() == {"name": "f1-strategy-analyst", "version": version("f1-strategy-analyst")}


def test_a_debrief_goes_through_its_stops_and_is_listed_where_it_stands(client: TestClient) -> None:
    started = client.post("/debriefs", json={"request": "Débrief de Monza"})
    assert started.status_code == 201
    debrief = started.json()
    assert (debrief["status"], debrief["waiting"]) == ("waiting", "plan")
    assert [item["id"] for item in client.get("/debriefs", params={"status": "waiting"}).json()] == [debrief["id"]]

    reviewed = client.post(f"/debriefs/{debrief['id']}/plan", json={"analyses": ["loss:LEC", "sc"]}).json()
    assert reviewed["waiting"] == "review"
    decisions = [{"point": point["id"], "action": "approve"} for point in reviewed["points"]]
    published = client.post(f"/debriefs/{debrief['id']}/review", json={"decisions": decisions}).json()

    assert published["status"] == "published" and published["deliverable"]
    assert client.get("/debriefs", params={"status": "waiting"}).json() == []
    assert [item["id"] for item in client.get("/debriefs", params={"status": "published"}).json()] == [debrief["id"]]


def test_each_decision_of_a_review_is_logged_with_the_agents_text(client: TestClient) -> None:
    debrief = client.post("/debriefs", json={"request": "Débrief de Monza"}).json()
    reviewed = client.post(f"/debriefs/{debrief['id']}/plan", json={"analyses": ["loss:LEC", "sc"]}).json()
    assert reviewed["facts"] and {fact["id"] for fact in reviewed["facts"]} >= {"loss:LEC"}
    first, second = reviewed["points"][:2]
    decisions = [
        {"point": first["id"], "action": "correct", "text": "Texte corrigé.", "reason": "wording"},
        {"point": second["id"], "action": "reject", "reason": "wrong_number"},
        *({"point": point["id"], "action": "approve"} for point in reviewed["points"][2:]),
    ]

    published = client.post(f"/debriefs/{debrief['id']}/review", json={"decisions": decisions}).json()

    assert [decision["action"] for decision in published["decisions"]][:2] == ["correct", "reject"]
    rejected = client.get("/decisions", params={"action": ["correct", "reject"]}).json()
    assert [(entry["action"], entry["reason"]) for entry in rejected] == [
        ("reject", "wrong_number"),
        ("correct", "wording"),
    ]
    assert rejected[1]["text_before"] == first["text"] and rejected[1]["text_after"] == "Texte corrigé."
    assert rejected[0]["decided_by"] == "analyste" and rejected[0]["subject"]["round"] == 16
    assert len(client.get("/decisions", params={"debrief": debrief["id"]}).json()) == len(decisions)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/debriefs", {"request": "Débrief de Monza"}),
        ("post", "/questions", {"question": "Qui a gagné à Monza ?"}),
        ("get", "/questions", None),
        ("get", "/decisions", None),
        ("post", "/debriefs/any/plan", {"analyses": []}),
        ("post", "/debriefs/any/review", {"decisions": []}),
        ("post", "/debriefs/any/questions", {"question": "Pourquoi ?"}),
    ],
)
def test_only_an_analyst_asks_or_decides(signed: TestClient, method: str, path: str, body: Any) -> None:
    def call(headers: dict[str, str]) -> int:
        return signed.request(method, path, json=body, headers=headers).status_code

    assert call({}) == 401
    assert call(as_reader()) == 403
    assert call(as_analyst()) not in (401, 403)
    signed.cookies.set("auth_token", token("a-reader"))  # the SSO's shared cookie, as a browser sends it
    assert call({}) == 403


def test_a_reader_sees_a_debrief_only_once_published(signed: TestClient) -> None:
    debrief = signed.post("/debriefs", json={"request": "Débrief de Monza"}, headers=as_analyst()).json()
    path = f"/debriefs/{debrief['id']}"
    assert signed.get(path).status_code == 404
    assert signed.get("/debriefs", params={"status": "waiting"}).json() == []
    assert signed.get(path, headers=as_analyst()).json()["waiting"] == "plan"

    reviewed = signed.post(f"{path}/plan", json={"analyses": ["loss:LEC", "sc"]}, headers=as_analyst()).json()
    decisions = [{"point": point["id"], "action": "approve"} for point in reviewed["points"]]
    signed.post(f"{path}/review", json={"decisions": decisions}, headers=as_analyst())

    assert signed.get(path).json()["status"] == "published"
    assert [item["id"] for item in signed.get("/debriefs").json()] == [debrief["id"]]
    assert signed.get(f"{path}/questions").json() == []
    entries = signed.get("/decisions", headers=as_analyst()).json()
    assert {entry["decided_by"] for entry in entries} == {"Ana Lyste"}


def test_the_session_names_the_account_and_says_when_the_api_is_open(signed: TestClient) -> None:
    assert signed.get("/me").json() == {"viewer": None, "open": False}
    assert signed.get("/me", headers=as_reader()).json()["viewer"]["analyst"] is False
    assert signed.get("/me", headers=as_analyst()).json()["viewer"]["name"] == "Ana Lyste"


def test_questions_on_a_published_debrief_show_only_backed_answers(client: TestClient) -> None:
    debrief = client.post("/debriefs", json={"request": "Débrief de Monza"}).json()
    asked = client.post(f"/debriefs/{debrief['id']}/questions", json={"question": "Combien a coûté l'arrêt ?"})
    assert asked.status_code == 409  # not published yet
    reviewed = client.post(f"/debriefs/{debrief['id']}/plan", json={"analyses": ["loss:LEC", "sc"]}).json()
    decisions = [{"point": point["id"], "action": "approve"} for point in reviewed["points"]]
    client.post(f"/debriefs/{debrief['id']}/review", json={"decisions": decisions})

    answered = client.post(f"/debriefs/{debrief['id']}/questions", json={"question": "Combien a coûté l'arrêt ?"})
    withheld = client.post(f"/debriefs/{debrief['id']}/questions", json={"question": "Et le second ?"}).json()
    refused = client.post(f"/debriefs/{debrief['id']}/questions", json={"question": "Et à Bakou ?"}).json()

    assert answered.status_code == 201
    reply = answered.json()
    assert reply["status"] == "answered" and reply["facts"] == [
        {
            "id": "loss:LEC",
            "label": "Arrêts de Leclerc",
            "ok": True,
            "error": None,
            "chart": {"kind": "positions", "drivers": ["LEC"], "reference": None, "from_lap": None, "to_lap": None},
        }
    ]
    assert (withheld["status"], withheld["points"]) == ("withheld", []) and "30" in withheld["reason"]
    assert refused["status"] == "refused"
    thread = client.get(f"/debriefs/{debrief['id']}/questions").json()
    assert [item["status"] for item in thread] == ["answered", "withheld", "refused"]


def test_a_free_question_is_answered_on_its_path_and_kept(client: TestClient) -> None:
    asked = client.post("/questions", json={"question": "Peut-on changer de pneus sous drapeau rouge ?"})
    started = client.post("/questions", json={"question": "Débrief du GP de Monza 2025"}).json()

    assert asked.status_code == 201
    rule = asked.json()
    assert (rule["route"], rule["status"], rule["sources"][0]["url"]) == ("rules", "answered", "https://www.fia.com/x")
    assert started["status"] == "debrief" and client.get(f"/debriefs/{started['debrief']}").json()["waiting"] == "plan"
    assert [row["id"] for row in client.get("/questions").json()] == [started["id"], rule["id"]]
    assert client.get(f"/questions/{rule['id']}").json()["points"][0]["text"] == "Oui, pendant la suspension."
    assert client.get("/questions/99").status_code == 404
    assert client.post("/questions", json={"question": "Qui a gagné ?", "season": 2025}).status_code == 422


def test_an_ambiguous_request_waits_for_a_clarification_answered_by_label(client: TestClient) -> None:
    debrief = client.post("/debriefs", json={"request": "Débrief du dernier GP"}).json()
    assert debrief["waiting"] == "clarification"
    assert [option["label"] for option in debrief["clarification"]["options"]] == ["Monza 2025", "Bakou 2025"]

    answered = client.post(f"/debriefs/{debrief['id']}/clarification", json={"option": "Monza 2025"}).json()

    assert answered["waiting"] == "plan" and answered["clarification"] is None


def test_a_question_carries_the_race_chosen_beside_it(client: TestClient) -> None:
    body = {"request": "Pourquoi Leclerc s'est-il arrêté si tôt ?", "season": 2025, "round": 16}

    debrief = client.post("/debriefs", json={**body, "question": True}).json()

    assert debrief["waiting"] == "plan"
    assert debrief["subject"]["question"] is True and debrief["subject"]["round"] == 16
    assert client.post("/debriefs", json={"request": "Pourquoi ?", "season": 2025}).status_code == 422


def test_an_answer_to_another_stop_is_refused(client: TestClient) -> None:
    debrief = client.post("/debriefs", json={"request": "Débrief de Monza"}).json()

    response = client.post(f"/debriefs/{debrief['id']}/review", json={"decisions": []})

    assert response.status_code == 409
    assert client.get("/debriefs/unknown").status_code == 404


def test_the_subject_is_shown_in_french_with_the_colour_of_the_team_followed() -> None:
    entry = [
        {"code": "LEC", "name": "Charles Leclerc", "team": "Ferrari"},
        {"code": "VER", "name": "Max Verstappen", "team": "Red Bull Racing"},
    ]
    raw = {"season": 2025, "round": 16, "event": "Italian Grand Prix", "kind": "team", "teams": ["Ferrari"]}

    shown = subject({**raw, "entry": entry, "focus": ["LEC"]})

    assert shown.grand_prix == "Grand Prix d'Italie"
    assert shown.colour == "#e8002d" and [driver.name for driver in shown.focus] == ["Charles Leclerc"]
    assert subject({}).grand_prix is None  # not resolved yet: the race is still to be chosen


def test_the_front_client_is_generated_from_this_api() -> None:
    # The front's client is generated from web/openapi.json: a schema changed here without `just web-gen-client`
    # would leave the front calling an API that no longer exists.
    assert OPENAPI.read_text() == openapi_document(), "the API changed: run `just web-gen-client` and commit web/"
