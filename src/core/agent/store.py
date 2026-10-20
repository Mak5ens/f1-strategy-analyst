"""Where an agent's requests live: LangGraph's checkpoints, the list of requests and the published deliverables, in
PostgreSQL.

A request waiting for a person is a checkpoint: restart the service, and `Agent.get` finds it where it stopped. The
requests (`RequestStore`, one row each, updated after every run) and the deliverables published are rows of their own,
to list without loading a graph.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.agent.chat import Reply
from core.agent.graph import Run
from core.agent.state import AgentState, Decision, Point, serializer


class PostgresSettings(BaseSettings):
    """Read from the environment (or `.env`) with the `POSTGRES_` prefix, as compose.yaml's database."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_", env_file=".env", extra="ignore")

    host: str = "localhost"
    port: int = 5435
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


_REQUESTS = """CREATE TABLE IF NOT EXISTS requests (
    thread_id text PRIMARY KEY,
    request text NOT NULL,
    subject jsonb NOT NULL,
    status text NOT NULL,
    waiting text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)"""


_DECISIONS = """CREATE TABLE IF NOT EXISTS decisions (
    id bigserial PRIMARY KEY,
    thread_id text NOT NULL,
    point text NOT NULL,
    action text NOT NULL,
    reason text,
    text_before text NOT NULL,
    text_after text,
    point_status text,
    decided_by text NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT now()
)"""


_QUESTIONS = """CREATE TABLE IF NOT EXISTS questions (
    id bigserial PRIMARY KEY,
    thread_id text NOT NULL,
    question text NOT NULL,
    status text NOT NULL,
    reply jsonb NOT NULL,
    asked_at timestamptz NOT NULL DEFAULT now()
)"""


class RequestStore:
    """Every request of an agent, where it stands: running, waiting for a person (and for what), stopped, published.

    `Agent(on_run=store.record)` keeps it up to date after each start and resume; the state itself stays in the
    checkpoints.
    """

    def __init__(self, settings: PostgresSettings | None = None) -> None:
        self._dsn = (settings or PostgresSettings()).dsn()
        with psycopg.connect(self._dsn, autocommit=True) as connection:
            connection.execute(_REQUESTS)
            connection.execute(_TABLE)
            connection.execute(_DECISIONS)
            connection.execute(_QUESTIONS)
            # The deliverables published before this table existed are requests too.
            connection.execute(
                "INSERT INTO requests (thread_id, request, subject, status, created_at, updated_at) "
                "SELECT thread_id, request, subject, 'published', published_at, published_at FROM published "
                "ON CONFLICT (thread_id) DO NOTHING"
            )

    def record(self, run: Run) -> None:
        with psycopg.connect(self._dsn, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO requests (thread_id, request, subject, status, waiting) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (thread_id) DO UPDATE SET subject = EXCLUDED.subject, status = EXCLUDED.status, "
                "waiting = EXCLUDED.waiting, updated_at = now()",
                (
                    run.thread_id,
                    run.state.request,
                    Jsonb(run.state.subject),
                    run.status,
                    run.waiting.kind if run.waiting else None,
                ),
            )

    def log_decisions(self, thread_id: str, points: Sequence[Point], decisions: Sequence[Decision], *, by: str) -> None:
        """The review's journal: who decided what on each point, why, and the agent's text before any correction."""
        drafted = {point.id: point for point in points}
        with psycopg.connect(self._dsn, autocommit=True) as connection, connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO decisions (thread_id, point, action, reason, text_before, text_after, point_status, "
                "decided_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        thread_id,
                        decision.point,
                        decision.action,
                        decision.reason,
                        drafted[decision.point].text if decision.point in drafted else "",
                        decision.text if decision.action == "correct" else None,
                        drafted[decision.point].status if decision.point in drafted else None,
                        by,
                    )
                    for decision in decisions
                ],
            )

    def save_reply(self, thread_id: str, reply: Reply) -> dict[str, Any]:
        """A question asked on a deliverable and its reply, whatever it is (answered, withheld, refused, stopped)."""
        with psycopg.connect(self._dsn, autocommit=True, row_factory=dict_row) as connection:
            row = connection.execute(
                "INSERT INTO questions (thread_id, question, status, reply) VALUES (%s, %s, %s, %s) RETURNING *",
                (thread_id, reply.question, reply.status, Jsonb(reply.model_dump(mode="json"))),
            ).fetchone()
        assert row is not None
        return dict(row)

    def replies(self, thread_id: str) -> list[dict[str, Any]]:
        """The questions asked on a deliverable, the first first."""
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT * FROM questions WHERE thread_id = %s ORDER BY asked_at, id", (thread_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    # Before `list`, which hides the built-in in the class body.
    def decisions(
        self, *, thread_id: str | None = None, actions: Sequence[str] | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        """The journal, the latest first, with each request's text and subject: of one request, or of some actions."""
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT d.*, r.request, r.subject FROM decisions d JOIN requests r USING (thread_id) "
                "WHERE (%(thread)s::text IS NULL OR d.thread_id = %(thread)s) "
                "AND (%(actions)s::text[] IS NULL OR d.action = ANY(%(actions)s)) "
                "ORDER BY d.decided_at DESC, d.id DESC LIMIT %(limit)s",
                {"thread": thread_id, "actions": list(actions) if actions else None, "limit": limit},
            ).fetchall()
        return list(rows)

    def list(
        self, *, status: str | None = None, subject: dict[str, Any] | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """The latest requests first, all of them or those of one status (`waiting`, `published`...), and those whose
        subject holds the fields given (`subject={"season": 2025, "round": 16}`)."""
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT * FROM requests WHERE (%(status)s::text IS NULL OR status = %(status)s) "
                "AND subject @> %(subject)s ORDER BY updated_at DESC LIMIT %(limit)s",
                {"status": status, "subject": Jsonb(subject or {}), "limit": limit},
            ).fetchall()
        return list(rows)


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
