"""The evaluation dataset: one format for every family of cases, split into a development and a test set.

A case says what is asked, what is expected, and where the expectation comes from (`Origin`): computed from the data,
derived by a rule, written by hand, or drafted by a model. The harness (LAB-148) reads the same file for every tool:
`to_promptfoo` and `to_ragas` give each one its own shape.

The development set is for tuning prompts and calibrating thresholds; the test set is only for measuring. A case
goes to one or the other by a hash of its id and the seed, so adding cases never moves the others from one set to the
other, and rebuilding gives the same files byte for byte.
"""

import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Family = Literal[
    "data",  # a fact read from the data
    "computation",  # a number computed by a deterministic tool
    "strategy",  # why something happened in a race
    "regulation",  # a question on the rules, with its reference answer and source
    "retrieval",  # a question on the rules, with the sources expected among the passages found
    "out_of_corpus",  # the answer is in no document: the system must abstain
    "safety",  # a prompt injection: the system must not follow it
]
FAMILIES: tuple[Family, ...] = ("data", "computation", "strategy", "regulation", "retrieval", "out_of_corpus", "safety")
Split = Literal["dev", "test"]


class Origin(BaseModel):
    """Where the expected answer comes from."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["computed", "rule", "handwritten", "model_draft"]
    by: str  # the generator, the tool, the person or the model
    inputs: dict[str, Any] = Field(default_factory=dict)  # what it was computed or drafted from
    reviewed: bool  # checked by a person: a model draft or a rule's guess is not until then


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    family: Family
    question: str
    # The expected answer, in words: what a correct answer says.
    answer: str | None = None
    # For an exact or numeric check: the value, the tolerance on it, its unit.
    value: float | int | str | list[str] | None = None
    tolerance: float | None = None
    unit: str | None = None
    # Sources expected among the passages found, each as payload fields ({"season": 2025, "article": "55.14"}).
    sources: list[dict[str, Any]] = Field(default_factory=list)
    # The system must decline: nothing in the corpus answers, or the question asks it to break its rules.
    abstain: bool = False
    # For a safety case: what must never appear in the answer.
    must_not_contain: list[str] = Field(default_factory=list)
    origin: Origin
    tags: list[str] = Field(default_factory=list)
    split: Split | None = None


def assign_split(case_id: str, *, seed: int, dev_share: float) -> Split:
    """Development or test, by a hash of the id: stable whatever the other cases are."""
    digest = hashlib.sha256(f"{seed}:{case_id}".encode()).digest()
    return "dev" if int.from_bytes(digest[:8], "big") / 2**64 < dev_share else "test"


def split_cases(cases: Iterable[Case], *, seed: int, dev_share: float) -> list[Case]:
    """Every case with its split; a case that already has one keeps it (the development set of LAB-186 was tuned on,
    so it stays out of the test set)."""
    return [
        case if case.split else case.model_copy(update={"split": assign_split(case.id, seed=seed, dev_share=dev_share)})
        for case in cases
    ]


def check_unique(cases: Sequence[Case]) -> None:
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"case id {case.id} appears twice")
        seen.add(case.id)


def write_cases(path: Path, cases: Iterable[Case]) -> None:
    """One case per line, sorted by id, keys in a fixed order: the same cases give the same bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [case.model_dump_json(exclude_defaults=True) for case in sorted(cases, key=lambda case: case.id)]
    path.write_text("".join(f"{line}\n" for line in lines))


def read_cases(path: Path) -> list[Case]:
    return [Case.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def to_promptfoo(case: Case, assertions: str = "file://evals/promptfoo/assertions.js") -> dict[str, Any]:
    """A promptfoo test: the case's id and question as variables, its expectation as assertions. The checks are
    functions of `assertions` (numbers with a tolerance, French decimal comma and lap times accepted; abstention).
    A system that abstained answers "ABSTENTION..." (see `core.evals.harness`)."""
    asserts: list[dict[str, Any]] = []

    def check(function: str, **config: Any) -> dict[str, Any]:
        return {"type": "javascript", "value": f"{assertions}:{function}", **({"config": config} if config else {})}

    if case.abstain:
        asserts.append(check("abstains"))
    elif isinstance(case.value, int | float) and not isinstance(case.value, bool):
        asserts.append(check("numeric", value=case.value, tolerance=case.tolerance or 0))
    elif isinstance(case.value, str):
        asserts.append(check("contains_all", items=[case.value]))
    elif isinstance(case.value, list):
        asserts.append(check("contains_all", items=case.value))
    asserts.extend({"type": "not-icontains", "value": text} for text in case.must_not_contain)
    return {
        "description": case.id,
        "vars": {"id": case.id, "question": case.question},
        "assert": asserts,
        "metadata": {"family": case.family, "split": case.split},
    }


def to_ragas(case: Case) -> dict[str, Any]:
    """A Ragas sample: the question and the reference answer. The contexts come from the system under test."""
    return {"user_input": case.question, "reference": case.answer or ""}


def dataset_items(cases: Iterable[Case]) -> list[dict[str, Any]]:
    """Cases as Langfuse dataset items: the question as input, the expectation as expected output."""
    return [
        {
            "id": case.id,
            "input": {"question": case.question},
            "expected_output": json.loads(
                case.model_dump_json(include={"answer", "value", "tolerance", "unit", "sources", "abstain"})
            ),
            "metadata": {"family": case.family, "origin": case.origin.model_dump(), "tags": case.tags},
        }
        for case in cases
    ]


def push_to_langfuse(name: str, cases: Sequence[Case], *, description: str, client: Any = None) -> int:
    """Create or update the Langfuse dataset `name` with the cases. Items keep a stable id (the dataset's name and the
    case's), so a second push updates them instead of adding copies; an item whose case left the set is archived,
    so that runs keep their history but new runs skip it. Returns the number of items sent."""
    if client is None:
        from langfuse import Langfuse

        from core.tracing import LangfuseSettings

        settings = LangfuseSettings()
        if not (settings.public_key and settings.secret_key):
            raise RuntimeError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are needed to push a dataset")
        client = Langfuse(
            public_key=settings.public_key, secret_key=settings.secret_key.get_secret_value(), base_url=settings.host
        )
    client.create_dataset(name=name, description=description, metadata={"cases": len(cases)})
    items = dataset_items(cases)
    for item in items:
        client.create_dataset_item(
            dataset_name=name,
            id=f"{name}:{item['id']}",
            input=item["input"],
            expected_output=item["expected_output"],
            metadata=item["metadata"],
        )
    kept = {f"{name}:{item['id']}" for item in items}
    for old in client.get_dataset(name).items:
        if old.id not in kept and old.status != "ARCHIVED":
            client.create_dataset_item(
                dataset_name=name,
                id=old.id,
                input=old.input,
                expected_output=old.expected_output,
                metadata=old.metadata,
                status="ARCHIVED",
            )
    client.flush()
    return len(items)
