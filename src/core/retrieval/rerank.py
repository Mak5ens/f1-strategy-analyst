"""Reranking through the gateway's `rerank` alias: a cross-encoder rereads each (query, passage) pair.

The hybrid search compares vectors computed separately for the query and the passage: fast, but approximate. A
cross-encoder reads both together and scores how well the passage answers the query, which is slower, so it only
rereads the search's candidates. The gateway serves it (llmops-gateway, LAB-184), priced and traced per team.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI

from core.gateway import gateway_client


@dataclass(frozen=True)
class Ranked:
    index: int  # position in the documents given
    score: float  # relevance, between 0 and 1


class Reranker(Protocol):
    def rerank(self, query: str, documents: Sequence[str], *, session_id: str | None = None) -> list[Ranked]:
        """Every document, best first."""
        ...


class GatewayReranker:
    def __init__(self, client: OpenAI | None = None, *, model: str = "rerank") -> None:
        # The SDK has no rerank call, but its client posts anywhere on the gateway: with the team's key, its
        # retries, and the transport that waits out rate limits and names the end user, as for chat.
        self._client = client or gateway_client()
        self._model = model

    def rerank(self, query: str, documents: Sequence[str], *, session_id: str | None = None) -> list[Ranked]:
        if not documents:
            return []
        body: dict[str, object] = {"model": self._model, "query": query, "documents": list(documents)}
        if session_id:
            body["metadata"] = {"generation_name": "rerank", "session_id": session_id}
        answer: Any = self._client.post("/rerank", body=body, cast_to=object)
        ranked = [Ranked(int(item["index"]), float(item["relevance_score"])) for item in answer["results"]]
        if sorted(item.index for item in ranked) != list(range(len(documents))):
            raise ValueError(f"`{self._model}` did not score each of the {len(documents)} documents once")
        return sorted(ranked, key=lambda item: item.score, reverse=True)
