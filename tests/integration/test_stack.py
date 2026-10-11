"""The local stack answers: the gateway with the `f1` key (started from llmops-gateway), and Qdrant (`just up`)."""

import os

import httpx
import pytest

from core.gateway import gateway_client

pytestmark = pytest.mark.integration


def test_the_f1_key_sees_its_team_models() -> None:
    models = {model.id for model in gateway_client().models.list()}

    # config/tenants.yaml of llmops-gateway: the f1 team needs chat models and embeddings.
    assert {"chat-small", "embed"} <= models


def test_a_chat_call_goes_through_the_gateway() -> None:
    response = gateway_client().chat.completions.create(
        model="chat-small",
        messages=[{"role": "user", "content": "Réponds seulement par le mot OK."}],
        max_tokens=5,
        temperature=0,
    )

    assert response.choices[0].message.content
    # Spend is recorded on the team's key, which is what budgets need.
    assert response.usage is not None
    assert response.usage.total_tokens > 0


def test_an_embedding_call_goes_through_the_gateway() -> None:
    response = gateway_client().embeddings.create(model="embed", input="Safety car deployed, lap 23.")

    # granite-embedding:278m, the model behind `embed` in llmops-gateway.
    assert len(response.data[0].embedding) == 768


def test_qdrant_is_ready() -> None:
    port = os.environ.get("QDRANT_PORT", "6333")

    assert httpx.get(f"http://localhost:{port}/readyz", timeout=5).status_code == 200
