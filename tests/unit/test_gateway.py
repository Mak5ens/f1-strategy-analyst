import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx2
import pytest
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from core.gateway import (
    GatewaySettings,
    GatewayTransport,
    StructuredOutputError,
    complete_json,
    gateway_client,
    rate_limit_wait,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore the developer's environment and `.env`, so the tests only see what they set."""
    for name in ("GATEWAY_URL", "GATEWAY_API_KEY", "GATEWAY_TIMEOUT_SECONDS", "GATEWAY_MAX_RETRIES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(GatewaySettings.model_config, "env_file", None)


def test_client_points_at_the_gateway_with_the_team_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_URL", "http://gateway.test:4000")
    monkeypatch.setenv("GATEWAY_API_KEY", "sk-team-key")

    client = gateway_client()

    assert str(client.base_url).rstrip("/") == "http://gateway.test:4000"
    assert client.api_key == "sk-team-key"


def test_a_missing_key_fails_at_startup_not_at_the_first_call() -> None:
    with pytest.raises(ValidationError, match="api_key"):
        gateway_client()


def test_the_key_never_shows_in_logs_or_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_API_KEY", "sk-team-key")

    assert "sk-team-key" not in repr(GatewaySettings())


class Answer(BaseModel):
    season: int


def fake_client(*contents: str) -> tuple[OpenAI, list[dict[str, Any]]]:
    requests: list[dict[str, Any]] = []
    queue = list(contents)

    def create(**request: Any) -> SimpleNamespace:
        requests.append(request)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=queue.pop(0)))])

    return cast(OpenAI, SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))), requests


def test_complete_json_validates_and_labels_the_call() -> None:
    client, requests = fake_client('{"season": 2025}')
    answer = complete_json(client, model="chat-pro", system="S", user="U", schema=Answer, name="step", session_id="t")
    assert answer == Answer(season=2025)
    [request] = requests
    assert request["response_format"] == {"type": "json_object"}
    assert '"season"' in request["messages"][0]["content"]  # the schema is in the prompt
    assert request["extra_body"] == {"metadata": {"generation_name": "step", "session_id": "t"}}


def test_complete_json_shows_the_model_its_error_once_then_gives_up() -> None:
    client, requests = fake_client('{"season": "soon"}', '{"season": 2026}')
    assert complete_json(client, model="m", system="S", user="U", schema=Answer).season == 2026
    assert "not valid against the schema" in requests[1]["messages"][-1]["content"]
    client, _ = fake_client("nope", "still nope")
    with pytest.raises(StructuredOutputError, match="Answer in 2 attempts"):
        complete_json(client, model="m", system="S", user="U", schema=Answer)


NOW = datetime(2026, 10, 13, 22, 14, 16, tzinfo=UTC)
LIMITED = {"retry-after": "60", "reset_at": "2026-10-13 22:14:46 UTC"}


def transport(
    answers: list[httpx2.Response], **options: Any
) -> tuple[GatewayTransport, list[httpx2.Request], list[float]]:
    requests: list[httpx2.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return answers.pop(0)

    gateway = GatewayTransport(transport=httpx2.MockTransport(handler), sleep=sleeps.append, now=lambda: NOW, **options)
    return gateway, requests, sleeps


def test_a_rate_limited_call_waits_until_the_limit_resets_then_goes_through() -> None:
    gateway, requests, sleeps = transport([httpx2.Response(429, headers=LIMITED), httpx2.Response(200, json={})])

    with httpx2.Client(transport=gateway) as client:
        assert client.post("http://gateway.test/chat/completions", json={"model": "chat-pro"}).status_code == 200

    assert len(requests) == 2
    [wait] = sleeps
    assert 30 <= wait <= 31  # reset_at, 30 s away, rather than retry-after's 60


def test_a_rate_limit_that_outlasts_the_longest_wait_goes_back_to_the_caller() -> None:
    gateway, requests, sleeps = transport([httpx2.Response(429, headers=LIMITED)] * 4, max_wait=70)

    with httpx2.Client(transport=gateway) as client:
        assert client.post("http://gateway.test/embeddings", json={}).status_code == 429

    assert sum(sleeps) == pytest.approx(70)
    assert len(requests) == 4  # waits of 30 s, 30 s, then the 10 s left


@pytest.mark.parametrize(
    ("headers", "low", "high"),
    [
        ({"retry-after": "20"}, 20, 21),
        ({"reset_at": "2026-10-13 22:14:00 UTC"}, 1, 2),  # already past: try again soon
        ({"retry-after": "3600"}, 60, 61),
        ({}, 10, 11),
    ],
)
def test_the_wait_follows_the_gateway_within_bounds(headers: dict[str, str], low: float, high: float) -> None:
    assert low <= rate_limit_wait(httpx2.Headers(headers), NOW) <= high


def test_the_end_user_is_named_in_json_calls_that_do_not_name_one() -> None:
    gateway, requests, _ = transport([httpx2.Response(200, json={})] * 2, end_user="f1-rag")

    with httpx2.Client(transport=gateway) as client:
        client.post("http://gateway.test/rerank", json={"model": "rerank", "query": "q"})
        client.post("http://gateway.test/rerank", json={"model": "rerank", "user": "someone"})

    assert [json.loads(request.read())["user"] for request in requests] == ["f1-rag", "someone"]
    assert int(requests[0].headers["content-length"]) == len(requests[0].read())


def test_sdk_calls_go_through_the_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_API_KEY", "sk-team-key")
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        embedding = {"object": "embedding", "index": 0, "embedding": [0.1]}
        return httpx2.Response(200, json={"object": "list", "data": [embedding], "model": "embed", "usage": {}})

    client = gateway_client(end_user="f1-rag", transport=httpx2.MockTransport(handler))
    client.embeddings.create(model="embed", input=["x"])

    assert json.loads(requests[0].read())["user"] == "f1-rag"
