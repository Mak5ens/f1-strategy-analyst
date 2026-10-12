"""Reranking through the gateway's `rerank` alias: a cross-encoder rereads each (query, passage) pair.

The hybrid search compares vectors computed separately for the query and the passage: fast, but approximate. A
cross-encoder reads both together and scores how well the passage answers the query, which is slower, so it only
rereads the search's candidates. The gateway serves it (llmops-gateway, LAB-184), priced and traced per team.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from core.gateway import GatewaySettings
from core.http import RateLimitedClient


@dataclass(frozen=True)
class Ranked:
    index: int  # position in the documents given
    score: float  # relevance, between 0 and 1


class Reranker(Protocol):
    def rerank(self, query: str, documents: Sequence[str], *, session_id: str | None = None) -> list[Ranked]:
        """Every document, best first."""
        ...


class GatewayReranker:
    def __init__(
        self,
        settings: GatewaySettings | None = None,
        *,
        model: str = "rerank",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = settings or GatewaySettings()  # api_key comes from the environment
        self._model = model
        # A 429 (the team's rate limit) or a 5xx is retried after the gateway's Retry-After, as the OpenAI SDK
        # does for chat and embeddings.
        self._client = RateLimitedClient(
            settings.url,
            min_interval=0,
            max_retries=settings.max_retries,
            backoff=1.0,
            timeout=settings.timeout_seconds,
            headers={"Authorization": f"Bearer {settings.api_key.get_secret_value()}"},
            transport=transport,
        )

    def rerank(self, query: str, documents: Sequence[str], *, session_id: str | None = None) -> list[Ranked]:
        if not documents:
            return []
        body: dict[str, object] = {"model": self._model, "query": query, "documents": list(documents)}
        if session_id:
            body["metadata"] = {"generation_name": "rerank", "session_id": session_id}
        response = self._client.request("POST", "/rerank", json=body)
        assert response is not None  # only a 404 with missing_ok returns None
        ranked = [Ranked(int(item["index"]), float(item["relevance_score"])) for item in response.json()["results"]]
        if sorted(item.index for item in ranked) != list(range(len(documents))):
            raise ValueError(f"`{self._model}` did not score each of the {len(documents)} documents once")
        return sorted(ranked, key=lambda item: item.score, reverse=True)
