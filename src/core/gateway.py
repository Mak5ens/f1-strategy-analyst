"""Single entry point to the LLMs: every call goes through llmops-gateway (LiteLLM Proxy) with the team's key.

The app never talks to a model provider directly. The gateway decides which model serves an alias (`chat-small`,
`embed`...), applies the team's budget and rate limits, and traces the call to the team's Langfuse project.
"""

import json

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, SecretStr, ValidationError
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


class StructuredOutputError(RuntimeError):
    """The model did not return JSON matching the schema, even after being shown its error."""


def complete_json[T: BaseModel](
    client: OpenAI,
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    max_tokens: int = 800,
    name: str | None = None,
    session_id: str | None = None,
    attempts: int = 2,
) -> T:
    """One chat call whose answer must be a JSON object valid against `schema`, validated by Pydantic.

    JSON mode (`json_object`) rather than a strict JSON schema: every alias supports it, and small local models fed
    a strict schema can loop on an array until the timeout. The schema goes in the system prompt instead, and an
    invalid answer is sent back once with Pydantic's error. `max_tokens` bounds a model that loops anyway.
    `name` and `session_id` label the call in the gateway's Langfuse traces.
    """
    instructions = f"{system}\n\nAnswer with a single JSON object matching this JSON schema:\n{_schema_text(schema)}"
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": user},
    ]
    metadata = {key: value for key, value in (("generation_name", name), ("session_id", session_id)) if value}
    error = ""
    for _ in range(attempts):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            extra_body={"metadata": metadata} if metadata else None,
        )
        content = response.choices[0].message.content or ""
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            error = str(exc)
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That answer is not valid against the schema:\n{error}\nAnswer again."},
            ]
    raise StructuredOutputError(f"{model} gave no valid {schema.__name__} in {attempts} attempts: {error}")


def _schema_text(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), separators=(",", ":"))
