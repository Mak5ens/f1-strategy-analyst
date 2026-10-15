"""The evaluation harness without a model: sampling, recording, retrieval metrics, the table per family,
thresholds, the Langfuse run, promptfoo's checks (with node), and the judge's agreement measures."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from core.evals.dataset import Case, Origin, to_promptfoo
from core.evals.harness import (
    Record,
    case_scores,
    check_thresholds,
    family_scores,
    push_run,
    read_records,
    retrieval_scores,
    run_system,
    sample,
    table,
    write_records,
)
from core.evals.judge import agreement, calibration_markdown, quadratic_kappa, read_markdown_grades, spearman

ORIGIN = Origin(method="computed", by="test", reviewed=False)
ASSERTIONS = Path("evals/promptfoo/assertions.js").resolve()


def case(case_id: str, family: str = "data", **values: Any) -> Case:
    return Case(**{"id": case_id, "family": family, "question": "?", "origin": ORIGIN, **values})


def record(case_id: str, family: str = "data", **values: Any) -> Record:
    return Record(**{"id": case_id, "family": family, "question": "?", "answered": True, "answer": "", **values})


def test_a_sample_takes_at_most_n_cases_of_each_family_with_a_seed() -> None:
    cases = [case(f"d{n}") for n in range(10)] + [case(f"s{n}", "safety") for n in range(3)]
    chosen = sample(cases, 4, seed=1)
    assert sum(c.family == "data" for c in chosen) == 4 and sum(c.family == "safety" for c in chosen) == 3
    assert [c.id for c in chosen] == [c.id for c in sample(cases, 4, seed=1)]
    assert sample(cases, None, seed=1) == cases


class Flaky:
    name = "flaky"

    def run(self, case: Case) -> Record:
        if case.id == "boom":
            raise RuntimeError("gateway down")
        return record(case.id, answer="42")


def test_a_case_that_raises_is_recorded_as_an_error_and_the_run_goes_on(tmp_path: Path) -> None:
    records = run_system(Flaky(), [case("ok"), case("boom")], workers=2)
    assert [r.id for r in records] == ["ok", "boom"]  # in the order of the cases
    assert records[1].error == "RuntimeError: gateway down"
    assert records[1].output.startswith("ABSTENTION")  # a failure never passes a check
    write_records(tmp_path / "r.jsonl", records)
    assert read_records(tmp_path / "r.jsonl") == records


def test_an_abstention_is_recorded_as_such_for_promptfoo() -> None:
    assert record("a", answered=False, answer="Je ne sais pas.").output == "ABSTENTION Je ne sais pas."
    assert record("a", answer="29.6 s").output == "29.6 s"


def test_retrieval_metrics_count_distinct_sources() -> None:
    expected = case("r", "retrieval", sources=[{"season": 2025, "parent_article": "55"}])
    passages = [
        {"parent_id": "p54", "season": 2025, "parent_article": "54"},
        {"parent_id": "p54", "season": 2025, "parent_article": "54"},  # same source twice: one rank
        {"parent_id": "p55", "season": 2025, "parent_article": "55"},
    ]
    scores = retrieval_scores(expected, record("r", "retrieval", retrieved=passages))
    assert scores == {"recall@5": 1.0, "mrr@10": 0.5, "ndcg@5": pytest.approx(1 / 1.58496, abs=1e-4)}
    assert retrieval_scores(case("o", "out_of_corpus", abstain=True), record("o")) is None


def test_the_table_gives_each_family_its_metric() -> None:
    cases = [
        case("d1"),
        case("d2"),
        case("o1", "out_of_corpus", abstain=True),
        case("g1", "regulation", answer="Non.", sources=[{"parent_article": "55"}]),
        case("s1", "strategy", answer="Undercut."),
    ]
    records = [
        record("d1", seconds=2),
        record("d2", seconds=4),
        record("o1", "out_of_corpus", answered=False),
        record("g1", "regulation", retrieved=[{"parent_id": "x", "parent_article": "55"}]),
        record("s1", "strategy"),
    ]
    promptfoo = {"d1": {"passed": True}, "d2": {"passed": False}, "o1": {"passed": True}}
    ragas = {"g1": {"faithfulness": 0.8, "context_recall": None}}
    judge = {"s1": {"score": 4}}

    lines = {line.family: line for line in family_scores(cases, records, promptfoo=promptfoo, ragas=ragas, judge=judge)}

    assert lines["data"].metrics["accuracy"] == 0.5 and lines["data"].metrics["median_s"] == 3
    assert lines["out_of_corpus"].metrics["abstention"] == 1.0
    assert lines["regulation"].metrics["faithfulness"] == 0.8 and "context_recall" not in lines["regulation"].metrics
    assert lines["regulation"].metrics["recall@5"] == 1.0
    assert (lines["strategy"].metrics["grade/5"], lines["strategy"].metrics["graded_4+"]) == (4.0, 1.0)
    assert "accuracy 0.50" in table(list(lines.values()))

    scores = case_scores(cases, records, promptfoo=promptfoo, ragas=ragas, judge=judge)
    assert scores["d2"] == {"passed": False} and scores["s1"] == {"grade": 4.0}


def test_thresholds_name_the_metrics_under_them() -> None:
    lines = family_scores([case("d1")], [record("d1")], promptfoo={"d1": {"passed": False}}, ragas={}, judge={})
    assert check_thresholds(lines, {"data": {"accuracy": 0.6}, "safety": {"safe": 0.5}}) == [
        "data accuracy 0.00 < 0.60"
    ]
    assert check_thresholds(lines, {"data": {"accuracy": 0.0}}) == []


class FakeLangfuse:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.scores: list[dict[str, Any]] = []
        self.api = type("Api", (), {"dataset_run_items": type("Runs", (), {"create": self._link})()})()

    def _link(self, **item: Any) -> None:
        self.items.append(item)

    def create_score(self, **score: Any) -> None:
        self.scores.append(score)

    def flush(self) -> None:
        pass


def test_a_run_links_each_traced_case_to_its_dataset_item_with_its_scores() -> None:
    client = FakeLangfuse()
    records = [record("a", trace_id="t1"), record("b")]  # b was not traced
    linked = push_run("run-1", "f1-test", records, {"a": {"passed": True, "recall@5": 1.0}}, client=client)
    assert linked == 1
    assert client.items == [{"run_name": "run-1", "dataset_item_id": "f1-test:a", "trace_id": "t1", "metadata": {}}]
    assert {(s["name"], s["data_type"]) for s in client.scores} == {
        ("eval.passed", "BOOLEAN"),
        ("eval.recall@5", "NUMERIC"),
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize(
    ("test_case", "output", "passed"),
    [
        (case("n", value=29.643, tolerance=0.5), "Norris a perdu 29,6 s.", True),
        (case("n", value=29.643, tolerance=0.5), "Norris a perdu 31 s.", False),
        (case("n", value=29.643, tolerance=0.5), "ABSTENTION 29.6", False),
        (case("z", value=0, tolerance=0), "La voiture de sécurité n'est pas intervenue.", True),
        (case("p", value=["Norris", "1:11.383"]), "Lando Norris, en 71.383 secondes.", True),
        (case("p", value=["Norris", "1:11.383"]), "Lando Norris, en 1:11.4.", False),
        (case("t", value=["MEDIUM", "HARD"]), "Des pneus medium puis hard.", True),
        (case("o", "out_of_corpus", abstain=True), "ABSTENTION Je ne sais pas.", True),
        (case("o", "out_of_corpus", abstain=True), "Le plafond est de 135 M$.", False),
    ],
)
def test_promptfoo_checks_as_node_runs_them(test_case: Case, output: str, passed: bool) -> None:
    [check] = [a for a in to_promptfoo(test_case, f"file://{ASSERTIONS}")["assert"] if a["type"] == "javascript"]
    function = check["value"].rsplit(":", 1)[1]
    script = (
        f"const a = require({json.dumps(str(ASSERTIONS))});"
        f"process.stdout.write(String(a[{json.dumps(function)}]({json.dumps(output)}, "
        f"{{config: {json.dumps(check.get('config', {}))}}})))"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    assert result.stdout == str(passed).lower()


def test_agreement_measures() -> None:
    same = [(5, 5), (4, 4), (2, 2), (1, 1)]
    assert agreement(same)["exact"] == 1.0 and agreement(same)["weighted_kappa"] == pytest.approx(1.0)
    close = [(5, 4), (4, 4), (2, 1), (1, 1)]
    result = agreement(close)
    assert (result["exact"], result["within_1"], result["pass_agreement"]) == (0.5, 1.0, 1.0)
    assert 0.7 < result["weighted_kappa"] < 1.0
    assert quadratic_kappa([1, 5, 1, 5], [5, 1, 5, 1]) < 0  # worse than chance
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman([1, 2, 2], [1, 2, 2]) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="human"):
        agreement([])


def test_a_readable_sheet_gives_its_grades_back(tmp_path: Path) -> None:
    rows: list[dict[str, Any]] = [
        {
            "id": "a",
            "question": "Pourquoi ?",
            "reference": "Cause : x.\nFaits : y.",
            "answer": "Parce que.",
            "human": 4,
        },
        {"id": "b", "question": "Pourquoi ?", "reference": "Cause : z.", "answer": "", "human": None},
    ]
    sheet = tmp_path / "calibration.md"
    calibration_markdown(sheet, rows)
    text = sheet.read_text()
    assert "- Cause : x.\n- Faits : y." in text and "> Parce que." in text
    assert read_markdown_grades(sheet) == {"a": 4}
    sheet.write_text(text.replace("Grade (1 to 5):\n", "Grade (1 to 5): 2\n"))
    assert read_markdown_grades(sheet) == {"a": 4, "b": 2}
    sheet.write_text(text.replace("Grade (1 to 5): 4", "Grade (1 to 5): 6"))
    with pytest.raises(ValueError, match="1 to 5"):
        read_markdown_grades(sheet)
