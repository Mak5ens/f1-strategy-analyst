"""The links of a race's events to the FIA's texts (LAB-189): found by code in the index, never guessed."""

from types import SimpleNamespace
from typing import Any

from qdrant_client import models

from f1.race_rules import RaceRules

ARTICLES = [
    {"doc_type": "sporting_regulations", "season": "2025", "article": "55", "title": "Safety car", "page": "66",
     "url": "https://fia.example/2025.pdf"},
    {"doc_type": "sporting_regulations", "season": "2025", "article": "55", "title": "Safety car", "page": "64",
     "url": "https://fia.example/2025.pdf"},
    {"doc_type": "sporting_regulations", "season": "2025", "article": "49",
     "title": "Formation lap(s) behind the safety car", "page": "60", "url": "https://fia.example/2025.pdf"},
    {"doc_type": "sporting_regulations", "season": "2026", "article": "B5.14", "title": "Suspension Procedure(s)",
     "page": "48", "url": "https://fia.example/2026.pdf"},
]  # fmt: skip
DECISIONS = [
    {"doc_type": "stewards_decision", "season": 2025, "round": 16, "session": "Race", "driver_name": "Esteban Ocon",
     "penalty": "5 second time penalty. 1 penalty point.", "document_number": "38",
     "cited_articles": ["2 b) (International Sporting Code)"], "url": "https://fia.example/38.pdf"},
    {"doc_type": "stewards_decision", "season": 2025, "round": 16, "session": "Race", "driver_name": "Esteban Ocon",
     "penalty": "Driver: Warning.", "document_number": "39", "cited_articles": [], "url": "https://fia.example/39.pdf"},
    {"doc_type": "stewards_decision", "season": 2025, "round": 16, "session": "Qualifying",
     "driver_name": "Isack Hadjar", "penalty": "Required to start the Race from the pit lane.",
     "url": "https://fia.example/q.pdf"},
]  # fmt: skip


class FakeIndex:
    """`scroll` as Qdrant's: the points whose payload matches every condition, a page at a time."""

    def __init__(self, payloads: list[dict[str, Any]], *, down: bool = False) -> None:
        self.payloads, self.down, self.calls = payloads, down, 0

    def scroll(self, collection: str, *, scroll_filter: models.Filter, limit: int, offset: Any, **_: Any) -> Any:
        self.calls += 1
        if self.down:
            raise ConnectionError("qdrant down")
        conditions = scroll_filter.must or []
        found = [
            SimpleNamespace(payload=payload)
            for payload in self.payloads
            if all(payload.get(c.key) == c.match.value for c in conditions)  # type: ignore[union-attr]
        ]
        start = offset or 0
        following = start + limit if start + limit < len(found) else None
        return found[start : start + limit], following


def test_a_neutralization_links_to_its_article_at_its_first_page() -> None:
    rules = RaceRules(FakeIndex(ARTICLES + DECISIONS))  # type: ignore[arg-type]

    assert rules.article(2025, "safety_car") == {
        "label": "Article 55 du règlement sportif 2025",
        "url": "https://fia.example/2025.pdf#page=64",
    }
    assert rules.article(2026, "red_flag") == {
        "label": "Article B5.14 du règlement sportif 2026",
        "url": "https://fia.example/2026.pdf#page=48",
    }
    assert rules.article(2025, "virtual_safety_car") is None  # not in the index: no link


def test_a_penalty_links_to_the_decision_that_gave_it() -> None:
    index = FakeIndex(ARTICLES + DECISIONS)
    rules = RaceRules(index)  # type: ignore[arg-type]

    assert rules.decision(2025, 16, "Esteban Ocon", "time", 5) == {
        "label": "Décision n° 38 des commissaires · art. 2 b) du Code sportif international",
        "url": "https://fia.example/38.pdf",
    }
    assert rules.decision(2025, 16, "Esteban Ocon", "time", 10) is None  # no decision gives these seconds
    assert rules.decision(2025, 16, "Isack Hadjar", "drive_through", None) is None  # a qualifying decision
    assert index.calls == 1  # the round's decisions are read once


def test_an_index_out_of_reach_gives_no_links() -> None:
    rules = RaceRules(FakeIndex([], down=True))  # type: ignore[arg-type]

    assert rules.article(2025, "safety_car") is None
    assert rules.decision(2025, 16, "Esteban Ocon", "time", 5) is None
