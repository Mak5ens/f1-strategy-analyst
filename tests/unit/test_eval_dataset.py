"""The evaluation dataset's format: stable split, same bytes for the same cases, the shapes promptfoo, Ragas and
Langfuse read, and the retrieval cases read back by `just rag-eval`."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from core.evals.dataset import (
    Case,
    Origin,
    assign_split,
    check_unique,
    dataset_items,
    push_to_langfuse,
    read_cases,
    split_cases,
    to_promptfoo,
    to_ragas,
    write_cases,
)
from core.retrieval.evaluation import load_cases
from f1.evals import grand_prix
from f1.evals.draft import cited_sporting_article

COMPUTED = Origin(method="computed", by="test", inputs={"season": 2025}, reviewed=False)


def case(case_id: str, **values: Any) -> Case:
    return Case(**{"id": case_id, "family": "data", "question": "?", "origin": COMPUTED, **values})


def test_a_case_says_its_family_its_answer_and_where_it_comes_from() -> None:
    with pytest.raises(ValidationError):
        Case(id="x", family="data", question="?")  # type: ignore[call-arg]  # no origin
    with pytest.raises(ValidationError):
        case("x", family="trivia")
    with pytest.raises(ValidationError):
        case("x", expected="a field of the old format")


def test_the_split_of_a_case_depends_on_its_id_only() -> None:
    cases = [case(f"c{n}") for n in range(400)]
    first = {c.id: c.split for c in split_cases(cases, seed=146, dev_share=0.3)}
    more = {
        c.id: c.split for c in split_cases([*cases, *(case(f"new{n}") for n in range(50))], seed=146, dev_share=0.3)
    }
    assert all(more[case_id] == split for case_id, split in first.items())  # adding cases moves no other
    assert 0.24 < sum(split == "dev" for split in first.values()) / 400 < 0.36
    assert assign_split("c1", seed=146, dev_share=0.3) == first["c1"]


def test_a_case_that_has_a_split_keeps_it() -> None:
    [kept] = split_cases([case("tuned-on", split="dev")], seed=1, dev_share=0.0)
    assert kept.split == "dev"


def test_the_same_cases_give_the_same_bytes(tmp_path: Path) -> None:
    cases = [case("b", value=2, tolerance=0), case("a", value=["Norris", "1:18.792"])]
    write_cases(tmp_path / "one.jsonl", cases)
    write_cases(tmp_path / "two.jsonl", reversed(cases))
    assert (tmp_path / "one.jsonl").read_bytes() == (tmp_path / "two.jsonl").read_bytes()
    assert [c.id for c in read_cases(tmp_path / "one.jsonl")] == ["a", "b"]


def test_ids_are_unique() -> None:
    with pytest.raises(ValueError, match="twice"):
        check_unique([case("a"), case("a")])


def test_promptfoo_gets_assertions_from_the_expectation() -> None:
    numeric = to_promptfoo(case("time-lost", family="computation", value=21.4, tolerance=0.5), "file://a.js")
    assert numeric["vars"] == {"id": "time-lost", "question": "?"}
    assert numeric["assert"] == [
        {"type": "javascript", "value": "file://a.js:numeric", "config": {"value": 21.4, "tolerance": 0.5}}
    ]
    words = to_promptfoo(case("pole", value=["Norris", "1:18.792"]), "file://a.js")
    assert words["assert"][0]["config"] == {"items": ["Norris", "1:18.792"]}
    safety = to_promptfoo(case("inject", family="safety", must_not_contain=["PWNED"], abstain=True), "file://a.js")
    assert safety["assert"] == [
        {"type": "javascript", "value": "file://a.js:abstains"},
        {"type": "not-icontains", "value": "PWNED"},
    ]
    assert safety["metadata"]["family"] == "safety"


def test_ragas_gets_the_question_and_the_reference() -> None:
    sample = to_ragas(case("rule", family="regulation", question="Peut-on ?", answer="Non."))
    assert sample == {"user_input": "Peut-on ?", "reference": "Non."}


class FakeLangfuse:
    def __init__(self) -> None:
        self.datasets: list[str] = []
        self.items: dict[str, dict[str, Any]] = {}

    def create_dataset(self, *, name: str, **_: Any) -> None:
        self.datasets.append(name)

    def create_dataset_item(self, *, id: str, **item: Any) -> None:
        self.items[id] = item

    def get_dataset(self, name: str) -> Any:
        items = [SimpleNamespace(**{"status": None, **item, "id": id}) for id, item in self.items.items()]
        return SimpleNamespace(items=[item for item in items if item.id.startswith(f"{name}:")])

    def flush(self) -> None:
        pass


def test_a_second_push_updates_the_items_instead_of_copying_them() -> None:
    client = FakeLangfuse()
    cases = [case("a", value=1, tolerance=0), case("b", answer="x")]
    push_to_langfuse("f1-dev", cases, description="d", client=client)
    push_to_langfuse("f1-dev", cases, description="d", client=client)
    assert sorted(client.items) == ["f1-dev:a", "f1-dev:b"]
    item = client.items["f1-dev:a"]
    assert item["input"] == {"question": "?"}
    assert item["expected_output"]["value"] == 1
    assert item["metadata"]["origin"]["method"] == "computed"
    assert dataset_items([case("c")])[0]["metadata"]["family"] == "data"


def test_an_item_whose_case_left_the_set_is_archived() -> None:
    client = FakeLangfuse()
    push_to_langfuse("f1-dev", [case("a", answer="x"), case("b", answer="y")], description="d", client=client)
    push_to_langfuse("f1-dev", [case("a", answer="x")], description="d", client=client)
    assert client.items["f1-dev:b"]["status"] == "ARCHIVED"
    assert "status" not in client.items["f1-dev:a"]


def test_rag_eval_reads_the_rule_and_out_of_corpus_cases(tmp_path: Path) -> None:
    rows = [
        case("r", family="retrieval", sources=[{"season": 2025, "parent_article": "55"}]),
        case("g", family="regulation", answer="…", sources=[{"season": 2024, "parent_article": "54"}]),
        case("o", family="out_of_corpus", abstain=True),
        case("d", family="data", value=3),  # not a retrieval case
    ]
    path = tmp_path / "dev.jsonl"
    path.write_text("".join(json.dumps(row.model_dump(mode="json")) + "\n" for row in rows))
    cases = load_cases(path)
    assert [c.answerable for c in cases] == [True, True, False]


def test_grands_prix_are_named_in_french() -> None:
    assert grand_prix("Italian Grand Prix", 2025) == "Grand Prix d'Italie 2025"
    assert grand_prix("Some New Grand Prix", 2027) == "Some New Grand Prix 2027"


@pytest.mark.parametrize(
    ("cited", "article"),
    [
        ("33.4 (Sporting Regulations)", "33.4"),
        ("26.7 b) (Sporting Regulations)", "26.7"),
        ("B1.6.3a", "B1.6.3"),
        ("12.2.1 i) (International Sporting Code)", None),
    ],
)
def test_the_sporting_article_a_decision_applied(cited: str, article: str | None) -> None:
    assert cited_sporting_article(cited) == article
