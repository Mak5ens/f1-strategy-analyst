"""Index the FIA corpus of some seasons: `just corpus 2025`, or `f1-corpus 2024 2025 2026 --regulations-only`.

For each season: the last issue of the sporting regulations, then every stewards' decision published so far.
Downloads go through the FIA website's cache (`.cache/fia/`, 10 seconds between requests on the first run), and
the index only embeds the chunks whose text changed: a rerun without change computes no embedding.
"""

import argparse
import logging
import sys
import unicodedata
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import pypdf

from core.retrieval.index import Document, HybridIndex, SyncReport
from f1.corpus import fia_index
from f1.corpus.decisions import parse_decision
from f1.corpus.fia import FiaWebsite
from f1.corpus.regulations import parse_regulations
from f1.data.sources import FastF1Source

log = logging.getLogger("f1.corpus")


def read_pdf(path: Path) -> list[str]:
    return [page.extract_text() or "" for page in pypdf.PdfReader(path).pages]


def round_numbers(season: int, cache_dir: Path) -> dict[str, int]:
    """Grand Prix name -> round, from FastF1's schedule, to join decisions with the race data."""
    return {_name_key(event.event_name): event.round for event in FastF1Source(cache_dir).schedule(season)}


def _name_key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return plain.replace("grand prix", "").strip()


class CorpusIngester:
    def __init__(self, website: FiaWebsite, index: HybridIndex, fastf1_cache: Path = Path(".cache/fastf1")) -> None:
        self._website = website
        self._index = index
        self._fastf1_cache = fastf1_cache

    def regulations(self, season: int, *, refresh: bool = False) -> SyncReport:
        issue = self._website.latest_regulations(season, refresh=refresh)
        document = parse_regulations(
            read_pdf(self._website.download(issue.url)),
            season=season,
            issue=issue.issue,
            published=issue.published,
            url=issue.url,
        )
        return self._index.sync(document)

    def decisions(self, season: int, *, refresh: bool = False) -> tuple[list[SyncReport], list[str]]:
        rounds = round_numbers(season, self._fastf1_cache)
        reports, failures = [], []
        for decision in self._website.decisions(season, refresh=refresh):
            try:
                document: Document = parse_decision(
                    read_pdf(self._website.download(decision.url)),
                    season=season,
                    grand_prix=decision.event,
                    round_number=rounds.get(_name_key(decision.event)),
                    url=decision.url,
                    file_name=decision.file_name,
                )
                reports.append(self._index.sync(document))
            except Exception as error:
                log.warning("%s: %s: %s", decision.file_name, type(error).__name__, error)
                failures.append(decision.file_name)
        return reports, failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-corpus", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("seasons", nargs="+", type=int, help="e.g. 2025, or 2024 2025 2026")
    only = parser.add_mutually_exclusive_group()
    only.add_argument("--regulations-only", action="store_true")
    only.add_argument("--decisions-only", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="fetch the FIA's document lists again")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for noisy in ("httpx", "httpx2", "fastf1", "pypdf"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    index = fia_index()
    index.ensure_collections()
    website = FiaWebsite()
    ingester = CorpusIngester(website, index)
    failed = 0
    try:
        for season in args.seasons:
            if not args.decisions_only:
                report = ingester.regulations(season, refresh=args.refresh)
                log.info("%s sporting regulations: %s", season, _counts([report]))
            if not args.regulations_only:
                reports, failures = ingester.decisions(season, refresh=args.refresh)
                log.info("%s stewards' decisions: %d documents, %s", season, len(reports), _counts(reports))
                failed += len(failures)
    finally:
        website.close()
    log.info("index: %d chunks; %d documents failed", index.count(), failed)
    return 1 if failed else 0


def _counts(reports: list[SyncReport]) -> str:
    total: Counter[str] = Counter()
    for report in reports:
        total.update(embedded=report.embedded, unchanged=report.unchanged, deleted=report.deleted)
    return f"{total['embedded']} chunks embedded, {total['unchanged']} unchanged, {total['deleted']} deleted"


if __name__ == "__main__":
    sys.exit(main())
