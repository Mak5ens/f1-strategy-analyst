"""Tracing of the app's own steps in Langfuse: one trace per request, one span per step, scores on the trace.

The gateway already traces every model call (tokens, cost, latency) to the team's Langfuse project. What it cannot
see is the app's logic between calls: which passages the search found, why the pipeline abstained, which citation
failed its check. The app sends that to the same project with the team's Langfuse keys, and passes the trace id as
`session_id` to the gateway's calls, so a request's model calls and its steps appear together in Langfuse's session.

Without `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`, tracing is off and every call here does nothing.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse, propagate_attributes
from opentelemetry.sdk.trace.export import SpanExporter
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LangfuseSettings(BaseSettings):
    """Read from the environment (or `.env`) with the `LANGFUSE_` prefix: the team's project in Langfuse."""

    model_config = SettingsConfigDict(env_prefix="LANGFUSE_", env_file=".env", extra="ignore")

    host: str = "http://localhost:3100"
    public_key: str | None = None
    secret_key: SecretStr | None = None


class Step:
    """A span in progress: the step records what it produced, and any detail worth reading in the trace."""

    def __init__(self, span: Any) -> None:
        self._span = span

    def output(self, output: Any, **metadata: Any) -> None:
        if self._span is not None:
            self._span.update(output=output, metadata=metadata or None)

    def warn(self, message: str) -> None:
        if self._span is not None:
            self._span.update(level="WARNING", status_message=message)


class Tracer:
    def __init__(self, client: Langfuse | None) -> None:
        self._client = client
        self._root: Any = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @contextmanager
    def trace(self, name: str, input: Any) -> Iterator[str | None]:
        """Root span of a request; yields its trace id (None when tracing is off), to pass as session id."""
        if self._client is None:
            yield None
            return
        trace_id = self._client.create_trace_id()
        with (
            self._client.start_as_current_observation(
                name=name, as_type="chain", input=input, trace_context={"trace_id": trace_id}
            ) as root,
            propagate_attributes(session_id=trace_id, trace_name=name),
        ):
            self._root = root
            try:
                yield trace_id
            finally:
                self._root = None

    @contextmanager
    def step(self, name: str, input: Any = None) -> Iterator[Step]:
        """A span under the current trace; its latency is the time spent in the block."""
        if self._client is None:
            yield Step(None)
            return
        with self._client.start_as_current_observation(name=name, as_type="span", input=input) as span:
            yield Step(span)

    def output(self, output: Any) -> None:
        """Output of the current trace's root span (the request's answer)."""
        if self._root is not None:
            self._root.update(output=output)

    def score(self, name: str, value: float | bool | str, comment: str | None = None) -> None:
        """A score on the current trace: online quality signals (top rerank score, abstention, valid citations)."""
        if self._client is None:
            return
        if isinstance(value, bool):
            self._client.score_current_trace(name=name, value=float(value), data_type="BOOLEAN", comment=comment)
        elif isinstance(value, str):
            self._client.score_current_trace(name=name, value=value, data_type="CATEGORICAL", comment=comment)
        else:
            self._client.score_current_trace(name=name, value=value, data_type="NUMERIC", comment=comment)

    def flush(self) -> None:
        if self._client is not None:
            self._client.flush()


def tracer(settings: LangfuseSettings | None = None, *, exporter: SpanExporter | None = None) -> Tracer:
    """Tracer of the team's Langfuse project, or a tracer that does nothing when no keys are configured.

    `exporter` replaces the export to Langfuse (tests read the spans from memory).
    """
    settings = settings or LangfuseSettings()
    if exporter is None and not (settings.public_key and settings.secret_key):
        return Tracer(None)
    return Tracer(
        Langfuse(
            public_key=settings.public_key or "pk-test",
            secret_key=settings.secret_key.get_secret_value() if settings.secret_key else "sk-test",
            base_url=settings.host,
            span_exporter=exporter,
        )
    )
