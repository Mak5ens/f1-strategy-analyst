"""The gateway's rerank client against a fake gateway: request shape, order of the answer, rate limit."""

import httpx
import pytest
from pydantic import SecretStr

from core.gateway import GatewaySettings
from core.retrieval.rerank import GatewayReranker

SETTINGS = GatewaySettings(_env_file=None, url="http://gateway.test", api_key=SecretStr("sk-team"), max_retries=2)


def reranker(handler: httpx.MockTransport) -> GatewayReranker:
    return GatewayReranker(SETTINGS, transport=handler)


def test_scores_come_back_best_first_with_the_team_key() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-team"
        body = request.read().decode()
        assert '"model":"rerank"' in body.replace(" ", "")
        return httpx.Response(
            200, json={"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]}
        )

    ranked = reranker(httpx.MockTransport(answer)).rerank("question", ["a", "b"], session_id="trace")
    assert [(item.index, item.score) for item in ranked] == [(1, 0.9), (0, 0.1)]


def test_a_rate_limit_is_waited_out() -> None:
    calls = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})

    assert reranker(httpx.MockTransport(answer)).rerank("q", ["a"])[0].score == 0.5
    assert len(calls) == 2


def test_an_answer_missing_a_document_is_refused() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})

    with pytest.raises(ValueError, match="each of the 2"):
        reranker(httpx.MockTransport(answer)).rerank("q", ["a", "b"])
