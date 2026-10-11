import pytest
from pydantic import ValidationError

from core.gateway import GatewaySettings, gateway_client


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
