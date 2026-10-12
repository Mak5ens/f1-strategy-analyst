"""The hybrid index against Qdrant's in-memory mode, with a fake embedder that counts what it embeds."""

import hashlib
from collections.abc import Sequence

import pytest
from qdrant_client import QdrantClient, models

from core.retrieval.embeddings import SparseVector
from core.retrieval.index import Chunk, Document, HybridIndex, Parent

WORDS = ["safety", "car", "red", "flag", "tyres", "penalty", "pit", "lane", "55.1", "vsc"]


class FakeEmbedder:
    """Dense: a bag of known words. Sparse: one dimension per word. Enough for ranking to make sense."""

    name = "fake/10+fake"
    dense_size = len(WORDS)

    def __init__(self) -> None:
        self.embedded: list[str] = []

    def dense(self, texts: Sequence[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[float(word in text.lower().split()) + 0.01 for word in WORDS] for text in texts]

    def sparse(self, texts: Sequence[str]) -> list[SparseVector]:
        return [self.sparse_query(text) for text in texts]

    def sparse_query(self, text: str) -> SparseVector:
        indices = sorted({int(hashlib.md5(word.encode()).hexdigest()[:6], 16) for word in text.lower().split()})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


def regulations(season: int, safety_car_text: str = "the safety car may be deployed") -> Document:
    return Document(
        doc_id=f"sporting-regulations-{season}",
        metadata={"season": season, "doc_type": "sporting_regulations", "issue": 1},
        parents=[
            Parent("55", "55) SAFETY CAR\n55.1 ...\n55.2 ...", {"article": "55"}),
            Parent("57", "57) RED FLAG\n57.1 ...", {"article": "57"}),
        ],
        chunks=[
            Chunk("55.1", f"55.1 {safety_car_text}", "55", {"article": "55.1"}),
            Chunk("55.2", "55.2 vsc periods and pit lane rules", "55", {"article": "55.2"}),
            Chunk("57.1", "57.1 under red flag tyres may be changed", "57", {"article": "57.1"}),
        ],
    )


@pytest.fixture
def index() -> tuple[HybridIndex, FakeEmbedder]:
    embedder = FakeEmbedder()
    index = HybridIndex(
        QdrantClient(":memory:"),
        "fia",
        embedder,
        payload_indexes={"season": models.PayloadSchemaType.INTEGER},
    )
    index.ensure_collections()
    return index, embedder


def test_first_sync_embeds_every_chunk(index: tuple[HybridIndex, FakeEmbedder]) -> None:
    hybrid, _ = index
    report = hybrid.sync(regulations(2025))
    assert (report.embedded, report.unchanged, report.deleted) == (3, 0, 0)
    assert hybrid.count() == 3


def test_rerun_without_change_embeds_nothing(index: tuple[HybridIndex, FakeEmbedder]) -> None:
    hybrid, embedder = index
    hybrid.sync(regulations(2025))
    embedder.embedded.clear()
    report = hybrid.sync(regulations(2025))
    assert (report.embedded, report.unchanged, report.deleted) == (0, 3, 0)
    assert embedder.embedded == []


def test_a_new_issue_embeds_only_what_changed_and_drops_what_is_gone(
    index: tuple[HybridIndex, FakeEmbedder],
) -> None:
    hybrid, embedder = index
    hybrid.sync(regulations(2025))
    embedder.embedded.clear()
    first = regulations(2025, "the safety car will be deployed")
    new_issue = Document(
        first.doc_id, [*first.chunks[:1], first.chunks[2]], first.parents, {**first.metadata, "issue": 2}
    )
    report = hybrid.sync(new_issue)
    assert (report.embedded, report.unchanged, report.deleted) == (1, 1, 1)
    assert embedder.embedded == ["55.1 the safety car will be deployed"]
    hits = hybrid.search("red flag tyres")
    assert {hit.payload["issue"] for hit in hits} == {2}  # payload updated without embedding


def test_search_filtered_on_a_season_never_returns_another(index: tuple[HybridIndex, FakeEmbedder]) -> None:
    hybrid, _ = index
    hybrid.sync(regulations(2025))
    hybrid.sync(regulations(2026))
    season_2026 = models.Filter(must=[models.FieldCondition(key="season", match=models.MatchValue(value=2026))])
    hits = hybrid.search("safety car", query_filter=season_2026)
    assert hits
    assert {hit.payload["season"] for hit in hits} == {2026}
    assert hits[0].payload["article"] == "55.1"


def test_a_chunk_leads_to_its_parent(index: tuple[HybridIndex, FakeEmbedder]) -> None:
    hybrid, _ = index
    hybrid.sync(regulations(2025))
    (top, *_) = hybrid.search("red flag tyres")
    parent = hybrid.parent(top.payload["doc_id"], top.payload["parent_key"])
    assert parent is not None
    assert parent["text"].startswith("57) RED FLAG")
    assert parent["season"] == 2025


def test_inconsistent_documents_are_refused(index: tuple[HybridIndex, FakeEmbedder]) -> None:
    hybrid, _ = index
    document = regulations(2025)
    with pytest.raises(ValueError, match="unique"):
        hybrid.sync(Document(document.doc_id, [*document.chunks, document.chunks[0]], document.parents))
    with pytest.raises(ValueError, match="missing parents"):
        hybrid.sync(Document(document.doc_id, document.chunks, document.parents[:1]))


def test_several_queries_and_one_kind_of_vector(index: tuple[HybridIndex, FakeEmbedder]) -> None:
    hybrid, _ = index
    hybrid.sync(regulations(2025))
    # Variants of one question are fused: each finds its own paragraph.
    keys = {hit.payload["key"] for hit in hybrid.search(["red flag tyres", "vsc pit lane"], limit=2)}
    assert keys == {"57.1", "55.2"}
    # Ablation: each kind of vector alone still ranks.
    assert hybrid.search("red flag tyres", sparse=False)[0].payload["key"] == "57.1"
    assert hybrid.search("red flag tyres", dense=False)[0].payload["key"] == "57.1"
    with pytest.raises(ValueError, match="one kind of vector"):
        hybrid.search("red flag", dense=False, sparse=False)


def test_lookup_finds_by_metadata_without_vectors(index: tuple[HybridIndex, FakeEmbedder]) -> None:
    hybrid, embedder = index
    hybrid.sync(regulations(2025))
    embedder.embedded.clear()
    article = models.Filter(must=[models.FieldCondition(key="article", match=models.MatchValue(value="55.2"))])
    [hit] = hybrid.lookup(article)
    assert hit.payload["key"] == "55.2"
    assert embedder.embedded == []
    assert hybrid.parent_by_id(hit.payload["parent_id"]) == hybrid.parent(hit.payload["doc_id"], "55")


def test_values_of_a_field(index: tuple[HybridIndex, FakeEmbedder]) -> None:
    hybrid, _ = index
    hybrid.sync(regulations(2025))
    hybrid.sync(regulations(2026))
    assert hybrid.values("season") == [2025, 2026]
