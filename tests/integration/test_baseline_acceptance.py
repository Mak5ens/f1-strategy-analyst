"""Acceptance of the reference system (LAB-147), on the FIA index, the lake, the gateway's chat-pro and Langfuse.

- Every answer cites its sources, and its numbers come from a tool, never from the model alone.
- The Langfuse trace of a question shows the search, the tool called and the generation.
"""

import time

import httpx
import pytest

from core.baseline import Baseline
from core.numbers import unverified_numbers
from core.tracing import LangfuseSettings
from f1.baseline import baseline as make_baseline
from f1.data import connect

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def baseline() -> Baseline:
    system = make_baseline()
    if not system.index.exists() or system.index.count() == 0:
        pytest.skip("empty FIA index: run `just corpus 2024 2025 2026` first")
    if not connect().execute("SELECT 1 FROM sessions WHERE season = 2025 AND round = 16").fetchall():
        pytest.skip("2025 not in the lake: run `just ingest 2025`")
    return system


def test_a_number_of_a_race_comes_from_a_tool(baseline: Baseline) -> None:
    result = baseline.answer(
        "Combien de temps Lando Norris a-t-il perdu lors de son 1er arrêt au Grand Prix d'Italie 2025 ?"
    )

    assert result.answered, result.problems
    tools = [call.tool for call in result.tool_calls]
    assert "pit_stop_loss" in tools, tools
    [loss] = [call.output for call in result.tool_calls if call.tool == "pit_stop_loss" and call.output]
    assert f"{loss['stops'][0]['time_lost_s']:.1f}" in result.answer.replace(",", ".")
    assert unverified_numbers(result.answer, [call.output for call in result.tool_calls]) == []


def test_a_question_on_the_rules_is_answered_with_its_sources(baseline: Baseline) -> None:
    result = baseline.answer(
        "En 2025, une équipe peut-elle changer les pneus pendant que la course est suspendue au drapeau rouge ?"
    )

    assert result.answered, result.problems
    assert result.sources, "the answer cites no source"
    assert {source.payload["season"] for source in result.sources} == {2025}
    assert all(source in result.retrieved for source in result.sources)


def test_the_trace_shows_the_search_the_tools_and_the_generation(baseline: Baseline) -> None:
    settings = LangfuseSettings()
    if not (settings.public_key and settings.secret_key):
        pytest.skip("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are not set")
    result = baseline.answer(
        "Combien de fois la voiture de sécurité est-elle intervenue au Grand Prix d'Australie 2025 ?"
    )
    assert result.trace_id and result.tool_calls

    auth = (settings.public_key, settings.secret_key.get_secret_value())
    deadline, names = time.monotonic() + 60, set()
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{settings.host}/api/public/v2/observations",
            params={"traceId": result.trace_id, "fields": "core,basic"},
            auth=auth,
            timeout=30,
        )
        response.raise_for_status()
        names = {observation["name"] for observation in response.json()["data"]}
        if {"baseline", "generate"} <= names:
            break
        time.sleep(1)

    assert {"baseline", "search", "generate"} <= names
    assert {f"tool:{call.tool}" for call in result.tool_calls} <= names
