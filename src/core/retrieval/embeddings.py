"""Embeddings of the hybrid index: dense through the gateway (meaning), sparse BM25 on the host (exact terms)."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastembed import SparseTextEmbedding
from openai import OpenAI

from core.gateway import gateway_client

BATCH_SIZE = 32


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


class Embedder(Protocol):
    @property
    def name(self) -> str:
        """Identifies the models: a change of name means every stored vector must be recomputed."""
        ...

    @property
    def dense_size(self) -> int: ...

    def dense(self, texts: Sequence[str]) -> list[list[float]]: ...

    def sparse(self, texts: Sequence[str]) -> list[SparseVector]: ...

    def sparse_query(self, text: str) -> SparseVector: ...


class GatewayEmbedder:
    """Dense vectors from the gateway's `embed` alias, BM25 sparse vectors computed locally with fastembed.

    BM25 needs no model call: it counts terms, and Qdrant applies the inverse document frequency at search time
    (the sparse vector is configured with the IDF modifier), so adding documents never invalidates stored vectors.
    """

    def __init__(
        self,
        client: OpenAI | None = None,
        *,
        model: str = "embed",
        dense_size: int = 768,
        sparse_model: str = "Qdrant/bm25",
        cache_dir: Path = Path(".cache/fastembed"),
    ) -> None:
        self._client = client or gateway_client()
        self._model = model
        self._dense_size = dense_size
        self._sparse_model_name = sparse_model
        self._sparse = SparseTextEmbedding(sparse_model, cache_dir=str(cache_dir))

    @property
    def name(self) -> str:
        return f"{self._model}/{self._dense_size}+{self._sparse_model_name}"

    @property
    def dense_size(self) -> int:
        return self._dense_size

    def dense(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            response = self._client.embeddings.create(model=self._model, input=list(texts[start : start + BATCH_SIZE]))
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        for vector in vectors:
            if len(vector) != self._dense_size:
                raise ValueError(f"`{self._model}` returned {len(vector)} dimensions, expected {self._dense_size}")
        return vectors

    def sparse(self, texts: Sequence[str]) -> list[SparseVector]:
        return [
            SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())
            for embedding in self._sparse.embed(list(texts))
        ]

    def sparse_query(self, text: str) -> SparseVector:
        (embedding,) = list(self._sparse.query_embed(text))
        return SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())
