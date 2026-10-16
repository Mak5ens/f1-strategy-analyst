"""The F1 debrief agent (LAB-151): `core.agent`'s controlled graph with the F1 theme, its checkpoints in PostgreSQL.

with debrief_agent() as agent:
    run = agent.start("Débrief stratégique du GP d'Italie 2025 pour Ferrari", thread_id="...")
    run = agent.resume(run.thread_id, [...])  # the person's answer to run.waiting
"""

from collections.abc import Iterator
from contextlib import contextmanager

from core.agent import Agent, AgentLimits
from core.agent.store import PostgresSettings, PublishedStore, RequestStore, postgres_checkpointer
from core.gateway import gateway_client
from core.tracing import tracer
from f1.agent.theme import AgentModels, F1Theme
from f1.data import connect
from f1.tools import RaceData

# The gateway counts the agent's spend apart from the RAG's and the baseline's (`user` of each call).
END_USER = "f1-agent"

__all__ = ["END_USER", "AgentModels", "F1Theme", "debrief_agent"]


@contextmanager
def debrief_agent(*, limits: AgentLimits | None = None, postgres: PostgresSettings | None = None) -> Iterator[Agent]:
    from f1.rag import rag_pipeline

    theme = F1Theme(RaceData(connect()), llm=gateway_client(end_user=END_USER), rules=rag_pipeline)
    published, requests = PublishedStore(postgres), RequestStore(postgres)
    with postgres_checkpointer(postgres) as checkpointer:
        yield Agent(
            theme,
            checkpointer=checkpointer,
            tracer=tracer(),
            limits=limits,
            on_publish=published.save,
            on_run=requests.record,
        )
