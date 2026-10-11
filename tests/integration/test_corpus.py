"""Acceptance of the FIA corpus index (LAB-145), on the index `just corpus` built in the stack's Qdrant.

- A search filtered on a season never returns a chunk of another season.
- Every chunk leads back to its document (URL, issue) and its article, and to a parent that exists.
- Rerunning the ingestion without change computes no embedding.
"""

import pytest
from qdrant_client import models

from core.retrieval.index import HybridIndex
from f1.corpus import fia_index
from f1.corpus.fia import FiaWebsite
from f1.corpus.ingest import CorpusIngester

pytestmark = pytest.mark.integration

QUESTIONS = [
    "Can tyres be changed while the race is suspended?",
    "How many laps behind the safety car before the race resumes?",
    "pit lane speeding penalty",
    "VSC",
    "Article 55",
    "Quelle pénalité pour avoir provoqué une collision ?",
]


@pytest.fixture(scope="module")
def index() -> HybridIndex:
    index = fia_index()
    if not index.exists() or index.count() == 0:
        pytest.skip("empty FIA index: run `just corpus 2024 2025 2026` first")
    return index


def season_filter(season: int) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="season", match=models.MatchValue(value=season))])


@pytest.mark.parametrize("season", [2024, 2025, 2026])
def test_a_season_filter_never_returns_another_season(index: HybridIndex, season: int) -> None:
    for question in QUESTIONS:
        hits = index.search(question, query_filter=season_filter(season), limit=50)
        assert hits, question
        assert {hit.payload["season"] for hit in hits} == {season}, question


def test_every_chunk_leads_to_its_document_and_article(index: HybridIndex) -> None:
    parents: set[str] = set()
    checked = 0
    for payload in index.chunk_payloads():
        assert payload["url"].startswith("https://www.fia.com/"), payload["key"]
        assert payload["doc_type"] in {"sporting_regulations", "stewards_decision"}
        if payload["doc_type"] == "sporting_regulations":
            assert payload["article"] and payload["issue"] and payload["page"], payload["key"]
        else:
            assert payload["grand_prix"] and payload["document_title"], payload["doc_id"]
        parents.add(payload["parent_id"])
        checked += 1
    assert checked == index.count()
    assert index.parents_exist(sorted(parents))


def test_reindexing_without_change_embeds_nothing(index: HybridIndex) -> None:
    website = FiaWebsite()
    try:
        report = CorpusIngester(website, index).regulations(2025)
    finally:
        website.close()
    assert report.embedded == 0 and report.deleted == 0
    assert report.unchanged > 300


def test_red_flag_question_finds_the_suspension_rules(index: HybridIndex) -> None:
    hits = index.search(
        "Can tyres be changed while the race is suspended under red flag?", query_filter=season_filter(2026)
    )
    assert any(hit.payload["article"].startswith("B5.14") for hit in hits[:3])
