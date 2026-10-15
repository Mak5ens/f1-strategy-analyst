"""Single entry point to the LLMs: every call goes through llmops-gateway (LiteLLM Proxy) with the team's key.

The app never talks to a model provider directly. The gateway decides which model serves an alias (`chat-small`,
`embed`...), applies the team's budget and rate limits, and traces the call to the team's Langfuse project.
"""

import json
import random
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx2
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


def gateway_client(
    settings: GatewaySettings | None = None,
    *,
    end_user: str | None = None,
    transport: httpx2.BaseTransport | None = None,
) -> OpenAI:
    """OpenAI client pointed at the gateway: chat, embeddings, reranking and the model list.

    `end_user` names the app in the gateway's cost metrics, and rate limits are waited out (`GatewayTransport`).
    `transport` replaces the network, for tests.
    """
    settings = settings or GatewaySettings()  # api_key comes from the environment
    return OpenAI(
        base_url=settings.url,
        api_key=settings.api_key.get_secret_value(),
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
        http_client=httpx2.Client(
            transport=GatewayTransport(end_user=end_user, transport=transport), timeout=settings.timeout_seconds
        ),
    )


@dataclass
class Usage:
    """Chat calls and their tokens, counted by the transport while a `usage_scope` is open."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


_USAGE: ContextVar[Usage | None] = ContextVar("gateway_usage", default=None)


@contextmanager
def usage_scope() -> Iterator[Usage]:
    """Count every chat call made in the block, on this thread, whatever client makes it (an agent's node and the
    retrieval pipeline it calls alike): an agent's budget per request is counted this way."""
    usage = Usage()
    token = _USAGE.set(usage)
    try:
        yield usage
    finally:
        _USAGE.reset(token)


# Longest wait for one rate-limited call: LiteLLM's limiter counts by the minute, so a few windows at most.
MAX_RATE_LIMIT_WAIT = 300.0


class GatewayTransport(httpx2.BaseTransport):
    """Transport of every call to the gateway: waits out its rate limit, and names the end user.

    The team's key is limited (60 requests and 100,000 tokens a minute for f1), and a question makes 4 to 6 calls,
    so an evaluation run reaches the limit. A 429 is back-pressure, not a failure: the call waits until the limit
    resets, as LiteLLM tells it in its `reset_at` header, else its `retry-after`, and is sent again, without spending
    the client's retries, until `max_wait` seconds have been spent waiting. Then the 429 goes back to the caller, and
    the SDK's own retries. (The OpenAI SDK runs on `httpx2`, hence its types here.)

    `end_user` is added as the `user` field of JSON calls that have none: the gateway counts cost per end user in
    its Prometheus metrics, which tells the spend of one app (the RAG, the agent) from the others sharing the key.
    """

    def __init__(
        self,
        *,
        end_user: str | None = None,
        max_wait: float = MAX_RATE_LIMIT_WAIT,
        transport: httpx2.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._end_user = end_user
        self._max_wait = max_wait
        self._transport = transport or httpx2.HTTPTransport()
        self._sleep = sleep
        self._now = now

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        request = self._with_end_user(request)
        waited = 0.0
        while True:
            response = self._transport.handle_request(request)
            if response.status_code != 429 or waited >= self._max_wait:
                if (usage := _USAGE.get()) is not None and request.url.path.endswith("/chat/completions"):
                    _count(usage, response)
                return response
            wait = min(rate_limit_wait(response.headers, self._now()), self._max_wait - waited)
            response.read()
            response.close()
            self._sleep(wait)
            waited += wait

    def close(self) -> None:
        self._transport.close()

    def _with_end_user(self, request: httpx2.Request) -> httpx2.Request:
        if not self._end_user or request.headers.get("content-type", "").split(";")[0] != "application/json":
            return request
        body = json.loads(request.read() or b"null")
        if not isinstance(body, dict) or "user" in body:
            return request
        headers = httpx2.Headers(request.headers)
        del headers["content-length"]
        return httpx2.Request(
            request.method,
            request.url,
            headers=headers,
            content=json.dumps({**body, "user": self._end_user}).encode(),
            extensions=request.extensions,
        )


def _count(usage: Usage, response: httpx2.Response) -> None:
    usage.calls += 1
    if response.status_code != 200:
        return
    try:
        counted = json.loads(response.read()).get("usage") or {}
    except ValueError:
        return
    usage.prompt_tokens += int(counted.get("prompt_tokens") or 0)
    usage.completion_tokens += int(counted.get("completion_tokens") or 0)


def key_spend(settings: GatewaySettings | None = None, *, transport: httpx2.BaseTransport | None = None) -> float:
    """What the team's key has spent so far, in dollars, as the gateway counts it (`/key/info` of the calling key).

    The gateway writes spend in batches, a few seconds after each call: read it again after a pause to be sure a run's
    last calls are counted."""
    settings = settings or GatewaySettings()
    with httpx2.Client(transport=transport, timeout=settings.timeout_seconds) as client:
        response = client.get(
            f"{settings.url.rstrip('/')}/key/info",
            headers={"Authorization": f"Bearer {settings.api_key.get_secret_value()}"},
        )
        response.raise_for_status()
    body = response.json()
    return float((body.get("info") or body).get("spend") or 0.0)


def rate_limit_wait(headers: httpx2.Headers, now: datetime) -> float:
    """Seconds until the gateway's rate limit resets: its `reset_at` (2026-10-13 22:15:17 UTC), else its
    `retry-after`, else 10 s; between 1 and 60 s, plus up to a second so parallel callers do not come back together."""
    try:
        wait = (
            datetime.strptime(headers["reset_at"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=UTC) - now
        ).total_seconds()
    except (KeyError, ValueError):
        try:
            wait = float(headers.get("retry-after", 10))
        except ValueError:
            wait = 10.0
    return min(max(wait, 1.0), 60.0) + random.uniform(0, 1)


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
