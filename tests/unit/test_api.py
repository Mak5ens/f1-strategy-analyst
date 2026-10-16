from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_agent import FakeTheme, agent

from core.agent import Agent, Run
from f1.api import app, get_agent, get_requests, openapi_document, subject

OPENAPI = Path(__file__).parents[2] / "web" / "openapi.json"


class FakeRequests:
    """The request store, in memory."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

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

    def list(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        rows = [row for row in self.rows.values() if status is None or row["status"] == status]
        return sorted(rows, key=lambda row: row["updated_at"], reverse=True)[:limit]


@pytest.fixture
def client() -> Iterator[TestClient]:
    requests = FakeRequests()
    bot: Agent = agent(FakeTheme())
    bot._on_run = requests.record
    app.dependency_overrides[get_agent] = lambda: bot
    app.dependency_overrides[get_requests] = lambda: requests
    yield TestClient(app)
    app.dependency_overrides.clear()


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


def test_an_ambiguous_request_waits_for_a_clarification_answered_by_label(client: TestClient) -> None:
    debrief = client.post("/debriefs", json={"request": "Débrief du dernier GP"}).json()
    assert debrief["waiting"] == "clarification"
    assert [option["label"] for option in debrief["clarification"]["options"]] == ["Monza 2025", "Bakou 2025"]

    answered = client.post(f"/debriefs/{debrief['id']}/clarification", json={"option": "Monza 2025"}).json()

    assert answered["waiting"] == "plan" and answered["clarification"] is None


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
