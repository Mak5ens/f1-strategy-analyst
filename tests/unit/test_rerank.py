"""The gateway's rerank client against a fake gateway: request shape, order of the answer, rate limit."""

import json

import httpx2
import pytest
from pydantic import SecretStr

from core.gateway import GatewaySettings, gateway_client
from core.retrieval.rerank import GatewayReranker

SETTINGS = GatewaySettings(_env_file=None, url="http://gateway.test", api_key=SecretStr("sk-team"), max_retries=2)


def reranker(handler: httpx2.MockTransport) -> GatewayReranker:
    return GatewayReranker(gateway_client(SETTINGS, end_user="f1-rag", transport=handler))


def test_scores_come_back_best_first_with_the_team_key() -> None:
    def answer(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/rerank"
        assert request.headers["Authorization"] == "Bearer sk-team"
        body = json.loads(request.read())
        assert (body["model"], body["user"], body["metadata"]["session_id"]) == ("rerank", "f1-rag", "trace")
        return httpx2.Response(
            200, json={"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]}
        )

    ranked = reranker(httpx2.MockTransport(answer)).rerank("question", ["a", "b"], session_id="trace")
    assert [(item.index, item.score) for item in ranked] == [(1, 0.9), (0, 0.1)]


def test_a_rate_limit_is_waited_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.gateway.time.sleep", lambda seconds: None)
    calls = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx2.Response(429, headers={"retry-after": "1"})
        return httpx2.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})

    assert reranker(httpx2.MockTransport(answer)).rerank("q", ["a"])[0].score == 0.5
    assert len(calls) == 2


def test_an_answer_missing_a_document_is_refused() -> None:
    def answer(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})

    with pytest.raises(ValueError, match="each of the 2"):
        reranker(httpx2.MockTransport(answer)).rerank("q", ["a", "b"])
