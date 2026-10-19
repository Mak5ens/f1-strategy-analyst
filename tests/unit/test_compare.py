"""The gate of the evaluation CI (LAB-149): a run compared with the reference on the same cases, the margin for the
noise of a few cases, the report for the pull request, the budget, and the key's spend."""

import json
from typing import Any

import httpx2
from pydantic import SecretStr

from core.evals.compare import compare, markdown
from core.evals.dataset import Case, Origin
from core.evals.harness import Record, run_system
from core.gateway import GatewaySettings, key_spend

ORIGIN = Origin(method="computed", by="test", reviewed=False)


def case(case_id: str, family: str) -> Case:
    return Case(id=case_id, family=family, question="?", origin=ORIGIN)


def test_a_sample_is_compared_with_the_reference_on_the_same_cases() -> None:
    cases = [case(f"d{n}", "data") for n in range(10)] + [case(f"s{n}", "strategy") for n in range(4)]
    scores: dict[str, dict[str, Any]] = {f"d{n}": {"passed": n < 7} for n in range(10)}
    scores |= {f"s{n}": {"grade": 2.0} for n in range(4)}
    # The reference passed 9 of the same 10 data cases, and graded the strategy cases 4; it has other cases too.
    reference: dict[str, dict[str, Any]] = {f"d{n}": {"passed": n < 9} for n in range(12)}
    strategy: dict[str, dict[str, Any]] = {f"s{n}": {"grade": 4.0} for n in range(4)}
    gated = {"data": ["accuracy"], "strategy": ["grade/5"], "safety": ["safe"]}

    data, grade = compare(cases, scores, {"data": ("main-data", reference), "strategy": ("main-s", strategy)}, gated)

    # Two cases lost of ten is the noise allowed: not a regression.
    assert (data.value, data.reference, data.cases, data.margin) == (0.7, 0.9, 10, 0.2)
    assert not data.regressed
    # Two points on a 5 scale, with a margin of two cases of four (0.5 x 5).
    assert (grade.delta, grade.margin, grade.regressed) == (-2.0, 2.5, False)
    worse = compare(cases, {**scores, "d5": {"passed": False}}, {"data": ("m", reference)}, gated)
    assert worse[0].regressed


def test_the_report_says_which_family_fell_and_by_how_much() -> None:
    cases = [case(f"d{n}", "data") for n in range(10)]
    reference: dict[str, dict[str, Any]] = {f"d{n}": {"passed": True} for n in range(10)}
    comparisons = compare(
        cases, {f"d{n}": {"passed": n < 5} for n in range(10)}, {"data": ("m", reference)}, {"data": ["accuracy"]}
    )

    text = markdown(comparisons, title="Evaluation", other_failures=["safety safe 0.40 < 0.50"], marker="<!-- x -->")

    assert text.startswith("<!-- x -->\n### Evaluation")
    assert "**2 check(s) failed**" in text
    assert "| data | accuracy | 10 | 0.50 | 1.00 | -0.50 | 0.20 | ❌ |" in text
    assert "**data** accuracy fell from 1.00 to 0.50 on the same 10 cases (-0.50), more than the 0.20 allowed." in text
    assert "- safety safe 0.40 < 0.50" in text


class Echo:
    name = "echo"

    def run(self, case: Case) -> Record:
        return Record(case.id, case.family, case.question, True, "42")


def test_cases_after_the_budget_are_not_run() -> None:
    runs = iter([None, "budget spent"])
    records = run_system(Echo(), [case("a", "data"), case("b", "data")], workers=1, stop=lambda: next(runs))
    assert [r.error for r in records] == [None, "not run: budget spent"]


def test_the_spend_is_read_from_the_key_info_of_the_calling_key() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url == "http://gateway.test:4000/key/info"
        assert request.headers["authorization"] == "Bearer sk-team"
        return httpx2.Response(200, content=json.dumps({"key": "sk-...", "info": {"spend": 0.42}}))

    settings = GatewaySettings(url="http://gateway.test:4000/", api_key=SecretStr("sk-team"))
    assert key_spend(settings, transport=httpx2.MockTransport(handler)) == 0.42


def test_models_side_by_side_with_latency_and_the_cost_of_answering() -> None:
    from core.evals.compare import side_by_side

    def report(model: str, accuracy: float, cost: float) -> dict[str, Any]:
        return {
            "run": f"run-{model}",
            "model": model,
            "families": {"data": {"cases": 20, "accuracy": accuracy, "answered": 1.0}},
            "latency_s": {"all": {"p50": 2.5, "p95": 9.04}},
            "system_cost_usd": cost,
        }

    table = side_by_side(
        [report("chat-medium", 0.5, 0.3), report("chat-pro", 0.8, 0.04)],
        {"data": ["accuracy"], "safety": ["safe"]},
        priced=lambda model: model == "chat-pro",
    )
    assert "| Family | Metric | `chat-medium` | `chat-pro` |" in table
    assert "| data | accuracy | 0.50 | 0.80 |" in table
    assert "safety" not in table  # no run scored it
    assert "| all | latency p95 | 9.0 s | 9.0 s |" in table
    assert "| all | cost of answering | local: the hardware's | $0.04 ($2.00 / 1,000 questions) |" in table


def test_latency_is_the_median_and_95th_percentile_of_a_question() -> None:
    from f1.evals.run import latency

    cases = [case(f"d{n}", "data") for n in range(20)]
    records = [Record(f"d{n}", "data", "?", True, "", seconds=float(n + 1)) for n in range(20)]
    assert latency(cases, records)["all"] == {"p50": 10.5, "p95": 19.0}


def test_each_system_has_its_own_thresholds_and_reference_runs(tmp_path: Any, monkeypatch: Any) -> None:
    import argparse

    from f1.evals import run

    monkeypatch.setattr(run, "THRESHOLDS", tmp_path / "thresholds")
    monkeypatch.setattr(run, "REPORTS", tmp_path)
    report = {"run": "agent-ref", "system": "agent", "families": {"data": {"cases": 40, "accuracy": 0.95}},
              "cases": {"d1": {"passed": True}}}  # fmt: skip
    (tmp_path / "agent-ref.json").write_text(json.dumps(report))

    run.thresholds(argparse.Namespace(from_report=str(tmp_path / "agent-ref.json"), system="baseline"))

    written = json.loads((tmp_path / "thresholds" / "agent.json").read_text())
    assert written["from_runs"] == {"data": "agent-ref"}
    assert 0.89 <= written["families"]["data"]["accuracy"] <= 0.9  # the score less the margin, rounded down
    assert not (tmp_path / "thresholds" / "baseline.json").exists()
    assert run.references("agent", ["data", "safety"]) == {"data": ("agent-ref", {"d1": {"passed": True}})}
    assert run.references("baseline", ["data"]) == {}
