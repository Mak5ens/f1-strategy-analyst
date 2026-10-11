"""The FIA website: where the sporting regulations and the stewards' decisions are found, and their download.

Politeness: fia.com's robots.txt asks for 10 seconds between requests; the client spaces every call by that much
and says who it is. Every download is cached under `.cache/fia/`: a document is fetched once, ever. The PDFs are
the FIA's: they stay in the cache, never in the repository.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from core.http import RateLimitedClient

BASE_URL = "https://www.fia.com"
REGULATIONS_PAGE = "/regulation/category/110"  # Formula 1 regulations, every season and issue
CHAMPIONSHIP_PAGE = "/documents/championships/fia-formula-one-world-championship-14"
USER_AGENT = "f1-strategy-analyst/0.1 (+https://github.com/Mak5ens/f1-strategy-analyst)"
CRAWL_DELAY_S = 10.0

# 2024-2025: fia_2025_formula_1_sporting_regulations_-_issue_5_-_2025-04-30.pdf
# 2026: fia_2026_f1_regulations_-_section_b_sporting_-_iss_09_-_2026-10-01.pdf
_REGULATION = re.compile(
    r"fia_(?P<season>\d{4})_(?:formula_1_sporting_regulations|f1_regulations_-_section_b_sporting)"
    r"_-_(?:issue|iss)_?(?P<issue>\d+)_-_(?P<date>\d{4}-\d{2}-\d{2})(?:_v(?P<version>\d+))?(?:_\d+)?\.pdf$"
)
_EVENT_LINK = re.compile(r'<a href="/decision-document-list/nojs/(\d+)"[^>]*>\s*([^<]+?)\s*</a>')
_SEASON_LINK = re.compile(r"/season/season-(\d{4})-(\d+)")
_DECISION_LINK = re.compile(r'href="(/system/files/decision-document/[^"]+\.pdf)"')
# Stewards' decisions and infringements; the deleted lap times are lists, not decisions.
_IS_DECISION = re.compile(r"_-_(?:decision|infringement)_-_(?!.*deleted_lap_times)")


@dataclass(frozen=True)
class RegulationIssue:
    season: int
    issue: int
    published: str  # YYYY-MM-DD
    url: str


@dataclass(frozen=True)
class DecisionDocument:
    season: int
    event: str  # as the FIA names it, e.g. "Italian Grand Prix"
    url: str

    @property
    def file_name(self) -> str:
        return unquote(Path(urlparse(self.url).path).name)


class FiaWebsite:
    def __init__(self, cache_dir: Path = Path(".cache/fia"), *, client: RateLimitedClient | None = None) -> None:
        self._cache = cache_dir
        self._http = client or RateLimitedClient(
            BASE_URL, min_interval=CRAWL_DELAY_S, timeout=60.0, headers={"User-Agent": USER_AGENT}
        )

    def latest_regulations(self, season: int, *, refresh: bool = False) -> RegulationIssue:
        """The last issue of the season's sporting regulations: the rules as they stood at the end of it."""
        page = self._cached_text("regulations.html", REGULATIONS_PAGE, refresh=refresh)
        issues = []
        for url in set(re.findall(r'href="([^"]+\.pdf)"', page)):
            match = _REGULATION.search(url)
            if match and int(match["season"]) == season:
                version = int(match["version"] or 0)
                issues.append((int(match["issue"]), match["date"], version, url))
        if not issues:
            raise LookupError(f"No {season} sporting regulations on {BASE_URL}{REGULATIONS_PAGE}")
        issue, date, _, url = max(issues)
        return RegulationIssue(season, issue, date, url if url.startswith("http") else BASE_URL + url)

    def decisions(self, season: int, *, refresh: bool = False) -> list[DecisionDocument]:
        """Stewards' decisions of every Grand Prix of the season published so far (tests excluded)."""
        seasons = dict(_SEASON_LINK.findall(self._cached_text("championship.html", CHAMPIONSHIP_PAGE, refresh=refresh)))
        if str(season) not in seasons:
            raise LookupError(f"No {season} season on {BASE_URL}{CHAMPIONSHIP_PAGE}")
        season_page = f"{CHAMPIONSHIP_PAGE}/season/season-{season}-{seasons[str(season)]}"
        # The season page changes during the season: always fetched for the current one.
        events = _EVENT_LINK.findall(self._cached_text(f"season-{season}.html", season_page, refresh=True))
        documents = []
        for event_id, name in events:
            if "test" in name.lower():
                continue
            for path in self._event_documents(season, event_id, refresh=refresh):
                if _IS_DECISION.search(path):
                    documents.append(DecisionDocument(season, name.strip(), BASE_URL + path))
        return documents

    def download(self, url: str) -> Path:
        """The PDF, from the cache when it was fetched before."""
        target = self._cache / "pdf" / unquote(Path(urlparse(url).path).name)
        if not target.exists():
            response = self._http.request("GET", url)
            assert response is not None
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_suffix(".part")
            partial.write_bytes(response.content)
            partial.rename(target)  # a crash mid-download never leaves a truncated PDF in the cache
        return target

    def close(self) -> None:
        self._http.close()

    def _event_documents(self, season: int, event_id: str, *, refresh: bool) -> list[str]:
        """Document links of one event. The page loads them with Drupal AJAX, which this call reproduces."""
        cached = self._cache / "events" / f"{season}-{event_id}.json"
        if cached.exists() and not refresh:
            paths: list[str] = json.loads(cached.read_text())
            return paths
        response = self._http.request(
            "POST", f"/decision-document-list/ajax/{event_id}", headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response is not None
        commands: list[dict[str, Any]] = response.json()
        html = "".join(command["data"] for command in commands if isinstance(command.get("data"), str))
        paths = sorted(set(_DECISION_LINK.findall(html)))
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(paths, indent=1))
        return paths

    def _cached_text(self, name: str, path: str, *, refresh: bool) -> str:
        cached = self._cache / name
        if cached.exists() and not refresh:
            return cached.read_text()
        response = self._http.request("GET", path)
        assert response is not None
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(response.text)
        return response.text
