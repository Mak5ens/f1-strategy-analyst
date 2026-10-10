"""Single entry point to the LLMs: every call goes through llmops-gateway (LiteLLM Proxy) with the team's key.

The app never talks to a model provider directly. The gateway decides which model serves an alias (`chat-small`,
`embed`...), applies the team's budget and rate limits, and traces the call to the team's Langfuse project.
"""

from openai import OpenAI
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    """Read from the environment (or `.env`) with the `GATEWAY_` prefix."""

    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    url: str = "http://localhost:4000"
    # The team's virtual key, never the gateway's master key.
    api_key: SecretStr
    timeout_seconds: float = 60.0
    # Retries of the OpenAI SDK on connection errors, 429 and 5xx. The gateway already falls back between models.
    max_retries: int = 2


def gateway_client(settings: GatewaySettings | None = None) -> OpenAI:
    """OpenAI client pointed at the gateway: chat, embeddings and the model list use the usual SDK calls."""
    settings = settings or GatewaySettings()  # api_key comes from the environment
    return OpenAI(
        base_url=settings.url,
        api_key=settings.api_key.get_secret_value(),
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )
