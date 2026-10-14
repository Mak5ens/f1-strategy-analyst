"""Retrieval evaluation: how well each configuration of the pipeline finds the expected sources, and where to put the
abstention threshold.

A case is a question and the sources expected for it, each described by payload fields ("the 2025 regulations,
article 55"); a case with no expected source is out of the corpus, and the pipeline should abstain on it. Sources
are counted as the model would get them: the distinct parents of the passages, pinned ones first.

The threshold is calibrated on a development set only. Calibrating on the test set would make its score a promise
the pipeline cannot keep on new questions.
"""

import json
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

from core.retrieval.pipeline import Passage, Retrieval


@dataclass(frozen=True)
class Case:
    question: str
    expected: Sequence[Mapping[str, Any]]  # empty: out of the corpus

    @property
    def answerable(self) -> bool:
        return bool(self.expected)


@dataclass(frozen=True)
class Outcome:
    case: Case
    rank: int | None  # rank of the first expected source among the distinct parents, None if not found
    top_score: float | None  # best rerank score; 1.0 when a passage was pinned (the gate lets it through)
    abstained: bool
    seconds: float


@dataclass(frozen=True)
class Report:
    name: str
    outcomes: Sequence[Outcome]
    metrics: Mapping[str, float] = field(default_factory=dict)


# The families of the evaluation dataset (core.evals.dataset) that retrieval is measured on: questions on the rules
# with their expected sources, and questions whose answer is in no document.
RETRIEVAL_FAMILIES = frozenset({"retrieval", "regulation", "out_of_corpus"})


def load_cases(path: Path) -> list[Case]:
    """The retrieval cases of a dataset file: its rule questions with their sources, and its out-of-corpus ones."""
    cases = []
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("family") in RETRIEVAL_FAMILIES:
                cases.append(Case(row["question"], row.get("sources", [])))
    return cases


def matches(payload: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(payload.get(key) == value for key, value in expected.items())


def source_rank(passages: Sequence[Passage], expected: Sequence[Mapping[str, Any]]) -> int | None:
    """Rank (from 1) of the first parent that holds an expected source, counting each parent once."""
    ordered = [p for p in passages if p.pinned] + [p for p in passages if not p.pinned]
    parents: list[str] = []
    for passage in ordered:
        parent = str(passage.payload.get("parent_id", passage.id))
        if parent not in parents:
            parents.append(parent)
        if any(matches(passage.payload, source) for source in expected):
            return parents.index(parent) + 1
    return None


def outcome(case: Case, retrieval: Retrieval, seconds: float) -> Outcome:
    rank = source_rank(retrieval.passages, case.expected) if case.answerable else None
    pinned = any(passage.pinned for passage in retrieval.passages)
    top_score = 1.0 if pinned else retrieval.top_score
    return Outcome(case, rank, top_score, retrieval.abstention is not None, seconds)


def with_threshold(outcomes: Sequence[Outcome], threshold: float) -> list[Outcome]:
    """The outcomes as the gate would have decided at this threshold (from a run with abstention off)."""
    return [
        Outcome(o.case, o.rank, o.top_score, o.top_score is None or o.top_score < threshold, o.seconds)
        for o in outcomes
    ]


def metrics(outcomes: Sequence[Outcome], k: int = 5) -> dict[str, float]:
    """Over the answerable cases: recall at 1 and k, and MRR at 10 (rank of the first expected source). Over all:
    correct abstentions (abstained exactly on the out-of-corpus cases), and the median latency."""
    answerable = [o for o in outcomes if o.case.answerable]
    out = [o for o in outcomes if not o.case.answerable]
    result: dict[str, float] = {}
    if answerable:
        result["recall@1"] = sum(o.rank == 1 for o in answerable) / len(answerable)
        result[f"recall@{k}"] = sum(o.rank is not None and o.rank <= k for o in answerable) / len(answerable)
        result["mrr@10"] = statistics.mean(1 / o.rank if o.rank and o.rank <= 10 else 0 for o in answerable)
        result["false_abstention"] = sum(o.abstained for o in answerable) / len(answerable)
    if out:
        result["correct_abstention"] = sum(o.abstained for o in out) / len(out)
    result["median_seconds"] = statistics.median(o.seconds for o in outcomes)
    return result


@dataclass(frozen=True)
class Calibration:
    threshold: float
    accuracy: float  # share of cases where "answer or abstain" was right, at that threshold
    answered_in_corpus: float
    abstained_out_of_corpus: float


def calibrate(outcomes: Sequence[Outcome], *, k: int = 5) -> Calibration:
    """The threshold on the top rerank score that best separates the cases to answer (expected source in the
    top k) from the cases to abstain on (out of the corpus, or the source was not found). Run with abstention off.

    Thresholds are tried halfway between consecutive scores, so a new question scoring like a known one does not
    fall on the edge. Ties go to the highest threshold: when two are as accurate, abstaining more is the safer error.
    """
    should_answer = [(o.top_score or 0.0, o.case.answerable and o.rank is not None and o.rank <= k) for o in outcomes]
    scores = sorted({score for score, _ in should_answer})
    candidates = [0.0] + [(low + high) / 2 for low, high in pairwise(scores)]
    best: Calibration | None = None
    for threshold in candidates:
        right = [(score >= threshold) == answer for score, answer in should_answer]
        to_answer = [score >= threshold for score, answer in should_answer if answer]
        to_abstain = [score < threshold for score, answer in should_answer if not answer]
        calibration = Calibration(
            threshold,
            sum(right) / len(right),
            sum(to_answer) / len(to_answer) if to_answer else 1.0,
            sum(to_abstain) / len(to_abstain) if to_abstain else 1.0,
        )
        if best is None or calibration.accuracy >= best.accuracy:
            best = calibration
    assert best is not None
    return best


def run(cases: Sequence[Case], retrieve: Callable[[str], tuple[Retrieval, float]]) -> list[Outcome]:
    """Run `retrieve` (question -> retrieval, seconds) on each case."""
    return [outcome(case, *retrieve(case.question)) for case in cases]
