"""Hybrid index in Qdrant, with parent/child chunks and incremental synchronization.

Two collections per index:
- `<name>_chunks`: the units of search (children), each with a dense vector (meaning) and a BM25 sparse vector
  (exact terms such as "55.1" or "VSC"), and a payload with its text, its parent and its document's metadata;
- `<name>_parents`: the context sent to the model (an article, a whole decision), fetched by id, no vectors.

`sync(document)` makes the index match a document: it embeds only the chunks whose content hash changed,
updates the payload of the others, and deletes the chunks the document no longer has. Rerunning an ingestion
without change computes no embedding.
"""

import hashlib
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient, models

from core.retrieval.embeddings import Embedder

# Bump to recompute every vector after a change of how chunks are embedded.
INDEX_VERSION = 1
_NAMESPACE = uuid.UUID("6f1c2a52-4d0e-4c63-9b51-0f8a6b0e7c11")
DENSE, SPARSE = "dense", "bm25"


@dataclass(frozen=True)
class Parent:
    key: str  # unique within the document
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    key: str  # unique within the document, stable across versions of it: it makes the point id
    text: str  # what is embedded
    parent_key: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Document:
    doc_id: str  # stable across versions: a new issue of a document replaces the old one
    chunks: Sequence[Chunk]
    parents: Sequence[Parent]
    metadata: Mapping[str, Any] = field(default_factory=dict)  # shared by its chunks and parents


@dataclass(frozen=True)
class SyncReport:
    doc_id: str
    embedded: int
    unchanged: int
    deleted: int


@dataclass(frozen=True)
class Hit:
    id: str
    score: float
    payload: dict[str, Any]


def point_id(doc_id: str, key: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{doc_id}/{key}"))


class HybridIndex:
    def __init__(
        self,
        client: QdrantClient,
        name: str,
        embedder: Embedder,
        *,
        payload_indexes: Mapping[str, models.PayloadSchemaType] | None = None,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self.chunks_collection = f"{name}_chunks"
        self.parents_collection = f"{name}_parents"
        self._payload_indexes = {"doc_id": models.PayloadSchemaType.KEYWORD, **(payload_indexes or {})}

    def ensure_collections(self) -> None:
        if not self._client.collection_exists(self.chunks_collection):
            self._client.create_collection(
                self.chunks_collection,
                vectors_config={
                    DENSE: models.VectorParams(size=self._embedder.dense_size, distance=models.Distance.COSINE)
                },
                sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
            )
        if not self._client.collection_exists(self.parents_collection):
            self._client.create_collection(self.parents_collection, vectors_config={})
        for collection in (self.chunks_collection, self.parents_collection):
            for field_name, schema in self._payload_indexes.items():
                self._client.create_payload_index(collection, field_name, field_schema=schema)

    def sync(self, document: Document) -> SyncReport:
        keys = [chunk.key for chunk in document.chunks]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{document.doc_id}: chunk keys must be unique")
        parent_keys = {parent.key for parent in document.parents}
        if missing := {chunk.parent_key for chunk in document.chunks} - parent_keys:
            raise ValueError(f"{document.doc_id}: chunks point to missing parents {sorted(missing)}")

        stored = dict(self._stored_hashes(self.chunks_collection, document.doc_id))
        wanted = {point_id(document.doc_id, chunk.key): chunk for chunk in document.chunks}
        payloads = {pid: self._chunk_payload(document, chunk) for pid, chunk in wanted.items()}
        to_embed = [pid for pid, payload in payloads.items() if stored.get(pid) != payload["content_hash"]]
        unchanged = [pid for pid in wanted if pid not in to_embed]

        for start in range(0, len(to_embed), 64):
            batch = to_embed[start : start + 64]
            texts = [wanted[pid].text for pid in batch]
            dense, sparse = self._embedder.dense(texts), self._embedder.sparse(texts)
            self._client.upsert(
                self.chunks_collection,
                [
                    models.PointStruct(
                        id=pid,
                        vector={
                            DENSE: dense_vector,
                            SPARSE: models.SparseVector(indices=sparse_vector.indices, values=sparse_vector.values),
                        },
                        payload=payloads[pid],
                    )
                    for pid, dense_vector, sparse_vector in zip(batch, dense, sparse, strict=True)
                ],
            )
        if unchanged:  # same text, maybe new metadata (a new issue number): no embedding, just the payload
            self._client.batch_update_points(
                self.chunks_collection,
                [
                    models.OverwritePayloadOperation(
                        overwrite_payload=models.SetPayload(payload=payloads[pid], points=[pid])
                    )
                    for pid in unchanged
                ],
            )
        stale = [pid for pid in stored if pid not in wanted]
        if stale:
            self._client.delete(self.chunks_collection, models.PointIdsList(points=stale))
        self._sync_parents(document)
        return SyncReport(document.doc_id, embedded=len(to_embed), unchanged=len(unchanged), deleted=len(stale))

    def search(self, query: str, *, query_filter: models.Filter | None = None, limit: int = 10) -> list[Hit]:
        """Plain hybrid search: dense and BM25 candidates fused by reciprocal rank. The production pipeline
        (query rewriting, reranking, abstention) builds on top of it."""
        sparse = self._embedder.sparse_query(query)
        (dense,) = self._embedder.dense([query])
        response = self._client.query_points(
            self.chunks_collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE, filter=query_filter, limit=limit * 5),
                models.Prefetch(
                    query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                    using=SPARSE,
                    filter=query_filter,
                    limit=limit * 5,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [Hit(str(point.id), point.score, point.payload or {}) for point in response.points]

    def parent(self, doc_id: str, key: str) -> dict[str, Any] | None:
        points = self._client.retrieve(self.parents_collection, [point_id(doc_id, key)], with_payload=True)
        return dict(points[0].payload or {}) if points else None

    def count(self) -> int:
        return self._client.count(self.chunks_collection).count

    def exists(self) -> bool:
        return self._client.collection_exists(self.chunks_collection)

    def chunk_payloads(self) -> Iterator[dict[str, Any]]:
        """Every chunk's payload, for checks over the whole index."""
        offset: models.ExtendedPointId | None = None
        while True:
            points, offset = self._client.scroll(self.chunks_collection, limit=1000, offset=offset, with_payload=True)
            yield from (dict(point.payload or {}) for point in points)
            if offset is None:
                return

    def parents_exist(self, parent_ids: list[str]) -> bool:
        found = self._client.retrieve(self.parents_collection, parent_ids, with_payload=False)
        return len(found) == len(set(parent_ids))

    def _chunk_payload(self, document: Document, chunk: Chunk) -> dict[str, Any]:
        content_hash = hashlib.sha256(f"{INDEX_VERSION}\n{self._embedder.name}\n{chunk.text}".encode()).hexdigest()
        return {
            **document.metadata,
            **chunk.metadata,
            "doc_id": document.doc_id,
            "key": chunk.key,
            "parent_id": point_id(document.doc_id, chunk.parent_key),
            "parent_key": chunk.parent_key,
            "text": chunk.text,
            "content_hash": content_hash,
        }

    def _sync_parents(self, document: Document) -> None:
        wanted = {point_id(document.doc_id, parent.key): parent for parent in document.parents}
        for start in range(0, len(document.parents), 256):
            batch = list(wanted.items())[start : start + 256]
            self._client.upsert(
                self.parents_collection,
                [
                    models.PointStruct(
                        id=pid,
                        vector={},
                        payload={
                            **document.metadata,
                            **parent.metadata,
                            "doc_id": document.doc_id,
                            "key": parent.key,
                            "text": parent.text,
                        },
                    )
                    for pid, parent in batch
                ],
            )
        stale = [pid for pid, _ in self._stored_hashes(self.parents_collection, document.doc_id) if pid not in wanted]
        if stale:
            self._client.delete(self.parents_collection, models.PointIdsList(points=stale))

    def _stored_hashes(self, collection: str, doc_id: str) -> Iterator[tuple[str, str | None]]:
        document_filter = models.Filter(
            must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
        )
        offset: models.ExtendedPointId | None = None
        while True:
            points, offset = self._client.scroll(
                collection,
                scroll_filter=document_filter,
                with_payload=["content_hash"],
                with_vectors=False,
                limit=512,
                offset=offset,
            )
            for point in points:
                yield str(point.id), (point.payload or {}).get("content_hash")
            if offset is None:
                return
