"""Retrieval metrics and the calibration of the abstention threshold, on hand-made outcomes."""

import math

import pytest

from core.retrieval.evaluation import Case, Outcome, calibrate, metrics, source_rank, with_threshold
from core.retrieval.pipeline import Passage

ARTICLE_55 = [{"season": 2025, "parent_article": "55"}]


def passage(key: str, parent: str, *, season: int = 2025, pinned: bool = False) -> Passage:
    payload = {"key": key, "parent_id": parent, "parent_article": parent, "season": season}
    return Passage(key, payload, rank=1, pinned=pinned)


def outcome(answerable: bool, rank: int | None, score: float) -> Outcome:
    return Outcome(Case("?", ARTICLE_55 if answerable else []), rank, score, abstained=False, seconds=1.0)


def test_sources_are_ranked_by_distinct_parent() -> None:
    passages = [passage("54.1", "54"), passage("54.2", "54"), passage("57.1", "57"), passage("55.1", "55")]
    assert source_rank(passages, ARTICLE_55) == 3  # 54 once, then 57, then 55
    assert source_rank([passage("55.1", "55", season=2024)], ARTICLE_55) is None  # another season
    pinned = [passage("54.1", "54"), passage("55.14", "55", pinned=True)]
    assert source_rank(pinned, ARTICLE_55) == 1  # pinned first, as the model gets them


def test_metrics() -> None:
    outcomes = [outcome(True, 1, 0.9), outcome(True, 4, 0.5), outcome(True, None, 0.1), outcome(False, None, 0.0)]
    result = metrics(outcomes)
    assert result["recall@1"] == pytest.approx(1 / 3)
    assert result["recall@5"] == pytest.approx(2 / 3)
    assert result["mrr@10"] == pytest.approx((1 + 1 / 4) / 3)
    assert result["ndcg@5"] == pytest.approx((1 + 1 / math.log2(5)) / 3)  # ranks 1 and 4, one source each


def test_the_threshold_falls_between_the_scores_to_answer_and_to_abstain() -> None:
    outcomes = [
        outcome(True, 1, 0.9),
        outcome(True, 2, 0.3),
        outcome(True, None, 0.25),  # source not found: better abstain
        outcome(False, None, 0.05),
        outcome(False, None, 0.01),
    ]
    calibration = calibrate(outcomes)
    assert calibration.threshold == pytest.approx((0.25 + 0.3) / 2)
    assert calibration.accuracy == 1.0
    gated = metrics(with_threshold(outcomes, calibration.threshold))
    assert gated["correct_abstention"] == 1.0
    assert gated["false_abstention"] == pytest.approx(1 / 3)
