"""Acceptance of the production retrieval pipeline (LAB-186), on the FIA index, the gateway's models and Langfuse.

- A French question on a precise article gets that article, of the right season, cited.
- A question outside the corpus gets an abstention, never an invented answer.
- The Langfuse trace shows the six steps, with their latency.
"""

import time

import httpx
import pytest

from core.retrieval.pipeline import RetrievalPipeline
from core.tracing import LangfuseSettings
from f1.rag import rag_pipeline

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pipeline() -> RetrievalPipeline:
    pipeline = rag_pipeline()
    if not pipeline.index.exists() or pipeline.index.count() == 0:
        pytest.skip("empty FIA index: run `just corpus 2024 2025 2026` first")
    return pipeline


def test_a_question_on_an_article_cites_it_from_the_right_season(pipeline: RetrievalPipeline) -> None:
    answer = pipeline.answer("Que dit l'article 55.14 du règlement 2025 sur les voitures retardataires ?")

    assert answer.answered, answer.abstention
    cited = [passage.payload for source in answer.sources for passage in source.passages]
    assert any(payload.get("article") == "55.14" and payload["season"] == 2025 for payload in cited)
    assert {payload["season"] for payload in cited} == {2025}
    assert all(claim.sources for claim in answer.claims)


@pytest.mark.parametrize(
    "question",
    [
        "Quel est le plafond budgétaire des équipes de F1 en 2025 ?",
        "Qui a gagné le championnat du monde des pilotes 2024 ?",
        "Quelle est la règle du hors-jeu au football ?",
    ],
)
def test_a_question_outside_the_corpus_gets_an_abstention(pipeline: RetrievalPipeline, question: str) -> None:
    answer = pipeline.answer(question)

    assert not answer.answered
    assert answer.claims == []


def test_the_trace_shows_the_six_steps_with_their_latency(pipeline: RetrievalPipeline) -> None:
    settings = LangfuseSettings()
    if not (settings.public_key and settings.secret_key):
        pytest.skip("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are not set")
    answer = pipeline.answer("En 2026, les voitures retardataires peuvent-elles se dédoubler sous safety car ?")
    assert answer.trace_id
    assert answer.answered, answer.abstention  # an abstention would end the trace at the gate

    auth = (settings.public_key, settings.secret_key.get_secret_value())
    deadline, observations = time.monotonic() + 60, []
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{settings.host}/api/public/v2/observations",
            params={"traceId": answer.trace_id, "fields": "core,basic"},
            auth=auth,
            timeout=30,
        )
        response.raise_for_status()
        observations = response.json()["data"]
        if {"rag", "verify"} <= {observation["name"] for observation in observations}:
            break
        time.sleep(1)

    steps = {observation["name"]: observation for observation in observations}
    assert {"understand", "search", "rerank", "gate", "generate", "verify"} <= steps.keys()
    for name in ("understand", "search", "rerank", "gate", "generate", "verify"):
        assert steps[name]["latency"] is not None, name
