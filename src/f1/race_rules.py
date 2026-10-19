"""Where a race's events are in the FIA's texts (LAB-189), found by code in the index of the corpus, never by a model.

- A safety car, a VSC or a red flag: the article of that season's sporting regulations, found by its title ("Safety
  car", "Virtual safety car (VSC)", "Suspending a sprint session or a race" or "Suspension procedure(s)"), linked to
  its page in the FIA's PDF.
- A penalty: the stewards' decision of that race for that driver, whose penalty names the same seconds (or the same
  kind), linked to the FIA's document, with the articles it cites.

An event the index does not have keeps no link: a link is never guessed. The index is read once per season and
round, and an index that cannot be reached gives no links rather than no race.
"""

import logging
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from qdrant_client import QdrantClient, models

from f1.corpus import INDEX_NAME

log = logging.getLogger(__name__)

# The titles of each kind's article, lower case: 2024 and 2025 number them 55, 56 and 57; 2026 B5.13, B5.12, B5.14.
TITLES: dict[str, Callable[[str], bool]] = {
    "safety_car": lambda title: title in {"safety car", "safety car (sc)"},
    "virtual_safety_car": lambda title: title.startswith("virtual safety car"),
    "red_flag": lambda title: title.startswith(("suspending", "suspension procedure")),
}
# How a decision words each kind of penalty.
KINDS = {"drive_through": r"drive[- ]through", "stop_go": r"stop and go|stop[- ]go"}


class RaceRules:
    def __init__(self, client: QdrantClient, collection: str = f"{INDEX_NAME}_parents") -> None:
        self._client = client
        self._collection = collection
        self._articles: dict[int, list[Mapping[str, Any]]] = {}
        self._decisions: dict[tuple[int, int], list[Mapping[str, Any]]] = {}

    def article(self, season: int, kind: str) -> dict[str, str] | None:
        """The article of the season's sporting regulations on a kind of neutralization: its number, title, link."""
        matches = TITLES.get(kind)
        found = [
            payload
            for payload in self._read_articles(season)
            if matches and matches(str(payload.get("title", "")).lower())
        ]
        if not found:
            return None
        first = min(found, key=lambda payload: int(payload.get("page") or 0))
        return {
            "label": f"Article {first['article']} du règlement sportif {season}",
            "url": f"{first['url']}#page={first['page']}" if first.get("page") else str(first["url"]),
        }

    def decision(
        self, season: int, round_number: int, driver: str, kind: str, seconds: int | None
    ) -> dict[str, str] | None:
        """The stewards' decision of the race giving that driver that penalty."""
        wanted = rf"\b{seconds} second" if kind == "time" and seconds else KINDS.get(kind)
        found = [
            payload
            for payload in self._read_decisions(season, round_number)
            if payload.get("session") == "Race"
            and str(payload.get("driver_name", "")).lower() == driver.lower()
            and wanted
            and re.search(wanted, str(payload.get("penalty", "")), re.IGNORECASE)
        ]
        if len(found) != 1:
            return None
        (payload,) = found
        cited = ", ".join(_cited(str(article)) for article in payload.get("cited_articles") or [])
        number = payload.get("document_number")
        label = f"Décision n° {number} des commissaires" if number else "Décision des commissaires"
        return {"label": f"{label} · {cited}" if cited else label, "url": str(payload["url"])}

    def _read_articles(self, season: int) -> list[Mapping[str, Any]]:
        if season not in self._articles:
            self._articles[season] = [
                payload
                for payload in self._scroll([("doc_type", "sporting_regulations")])
                if str(payload.get("season")) == str(season)
            ]
        return self._articles[season]

    def _read_decisions(self, season: int, round_number: int) -> list[Mapping[str, Any]]:
        if (season, round_number) not in self._decisions:
            self._decisions[season, round_number] = [
                payload
                for payload in self._scroll([("doc_type", "stewards_decision"), ("round", round_number)])
                if str(payload.get("season")) == str(season)
            ]
        return self._decisions[season, round_number]

    def _scroll(self, conditions: Iterable[tuple[str, Any]]) -> list[Mapping[str, Any]]:
        query = models.Filter(
            must=[models.FieldCondition(key=key, match=models.MatchValue(value=value)) for key, value in conditions]
        )
        payloads: list[Mapping[str, Any]] = []
        offset = None
        try:
            while True:
                points, offset = self._client.scroll(
                    self._collection, scroll_filter=query, limit=256, offset=offset, with_vectors=False
                )
                payloads += [point.payload or {} for point in points]
                if offset is None:
                    return payloads
        except Exception as error:  # no index, no links: the race's page still shows
            log.warning("FIA index unreachable, events shown without links: %s", error)
            return []


# The texts a decision cites, as the site names them.
CODES = {
    "(International Sporting Code)": "du Code sportif international",
    "(Sporting Regulations)": "du règlement sportif",
}


def _cited(article: str) -> str:
    """ "2 b) (International Sporting Code)" -> "art. 2 b) du Code sportif international"."""
    for code, name in CODES.items():
        if article.endswith(code):
            return f"art. {article.removesuffix(code).strip()} {name}"
    return f"art. {article}"
