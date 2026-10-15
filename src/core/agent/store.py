"""Where an agent's requests live: LangGraph's checkpoints and the published deliverables, in PostgreSQL.

A request waiting for a person is a checkpoint: restart the service, and `Agent.get` finds it where it stopped. The
deliverables published are rows of their own, to list and read without loading a graph.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.agent.state import AgentState, serializer


class PostgresSettings(BaseSettings):
    """Read from the environment (or `.env`) with the `POSTGRES_` prefix, as compose.yaml's database."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_", env_file=".env", extra="ignore")

    host: str = "localhost"
    port: int = 5433
    user: str = "f1"
    password: SecretStr = SecretStr("")
    db: str = "f1"

    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.db}"


@contextmanager
def postgres_checkpointer(settings: PostgresSettings | None = None) -> Iterator[PostgresSaver]:
    """LangGraph's PostgreSQL checkpointer, its tables created on first use."""
    dsn = (settings or PostgresSettings()).dsn()
    with psycopg.Connection.connect(dsn, autocommit=True, prepare_threshold=0, row_factory=dict_row) as connection:
        saver = PostgresSaver(connection, serde=serializer())
        saver.setup()
        yield saver


_TABLE = """CREATE TABLE IF NOT EXISTS published (
    thread_id text PRIMARY KEY,
    request text NOT NULL,
    subject jsonb NOT NULL,
    deliverable text NOT NULL,
    decisions jsonb NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now()
)"""


class PublishedStore:
    """The deliverables an agent published, with the request, the subject and the review's decisions."""

    def __init__(self, settings: PostgresSettings | None = None) -> None:
        self._dsn = (settings or PostgresSettings()).dsn()
        with psycopg.connect(self._dsn, autocommit=True) as connection:
            connection.execute(_TABLE)

    def save(self, thread_id: str, state: AgentState) -> None:
        with psycopg.connect(self._dsn, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO published (thread_id, request, subject, deliverable, decisions) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (thread_id) DO UPDATE SET deliverable = EXCLUDED.deliverable, "
                "decisions = EXCLUDED.decisions, published_at = now()",
                (
                    thread_id,
                    state.request,
                    Jsonb(state.subject),
                    state.deliverable or "",
                    Jsonb([decision.model_dump() for decision in state.decisions]),
                ),
            )

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT thread_id, request, subject, published_at FROM published ORDER BY published_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return list(rows)

    def get(self, thread_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            row = connection.execute("SELECT * FROM published WHERE thread_id = %s", (thread_id,)).fetchone()
        return dict(row) if row else None
