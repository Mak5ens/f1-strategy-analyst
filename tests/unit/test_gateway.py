from types import SimpleNamespace
from typing import Any, cast

import pytest
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from core.gateway import GatewaySettings, StructuredOutputError, complete_json, gateway_client


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
