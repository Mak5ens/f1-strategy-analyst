"""Stewards' decision PDF -> one parent (the whole decision) and its children (summary, then reasons).

A decision is a one-page form: a header (event, document number, date), then labelled fields (No / Driver,
Competitor, Time, Session, Fact, Infringement or Offence, Decision, Reason), then a standard paragraph on the right
of appeal and the stewards' names, which are dropped. The summary child (who, what, which article, which penalty)
answers "what penalty did X get"; the reason children answer "why".
"""

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime

from core.retrieval.index import Chunk, Document, Parent
from f1.corpus.regulations import MAX_CHUNK_CHARS

FIELDS = ("No / Driver", "Competitor", "Time", "Session", "Fact", "Infringement", "Offence", "Decision", "Reason")
_FIELD = re.compile(rf"^({'|'.join(re.escape(field) for field in FIELDS)})\b\s*(.*)$")
_START = re.compile(r"determine the following|have considered the following", re.IGNORECASE)
_END = re.compile(r"^Competitors are reminded|^Decisions of the Stewards are taken independently", re.IGNORECASE)
_DOCUMENT = re.compile(r"^Document\s+(\d+)")
_DATE = re.compile(r"^Date\s+(\d{1,2} \w+ \d{4})")
_CAR = re.compile(r"^(\d{1,2})\s*[-\u2013]\s*(.+)$")  # hyphen or en dash
# "Article 33.4 of the FIA Formula 1 Sporting Regulations", "Article 12.2.1 i) of the International Sporting Code"
_ARTICLE = re.compile(r"Articles?\s+(B?\d+(?:\.\d+)*[a-z]?)(?:\s*([a-z]|[ivx]+)\))?")


def parse_decision(
    pages: Sequence[str], *, season: int, grand_prix: str, round_number: int | None, url: str, file_name: str
) -> Document:
    # NFKC turns the non-breaking spaces of the FIA's PDFs into plain spaces.
    lines = [
        clean for page in pages for line in page.splitlines() if (clean := unicodedata.normalize("NFKC", line).strip())
    ]
    header: dict[str, str] = {}
    fields: dict[str, list[str]] = {}
    current: str | None = None
    started = False
    for line in lines:
        if _END.search(line):
            break
        if not started:
            if match := _DOCUMENT.match(line):
                header["document_number"] = match[1]
            elif match := _DATE.match(line):
                header["date"] = match[1]
            started = bool(_START.search(line))
            continue
        if (match := _FIELD.match(line)) and match[1] not in fields:
            current = match[1]
            fields[current] = [match[2]] if match[2] else []
        elif current:
            fields[current].append(line)

    text = {name: " ".join(value).strip() for name, value in fields.items()}
    infringement = text.get("Infringement") or text.get("Offence")
    car, driver = None, None
    if (match := _CAR.match(text.get("No / Driver", ""))) is not None:
        car, driver = int(match[1]), match[2].strip()

    title = _title(file_name)
    metadata = {
        "doc_type": "stewards_decision",
        "season": season,
        "grand_prix": grand_prix,
        "round": round_number,
        "document_title": title,
        "document_number": header.get("document_number"),
        "published": _iso_date(header.get("date")),
        "session": text.get("Session"),
        "car_number": car,
        "driver_name": driver,
        "competitor": text.get("Competitor"),
        "penalty": text.get("Decision"),
        "cited_articles": cited_articles(infringement or ""),
        "url": url,
    }
    context = f"Stewards' decision, {season} {grand_prix}"
    if fields.get("Fact") and infringement and text.get("Decision"):
        who = f"Car {car} ({driver}, {text.get('Competitor')})" if car else text.get("No / Driver", "")
        summary = (
            f"{context}, {text.get('Session', 'session not stated')}: {who}.\n"
            f"Fact: {text['Fact']}\nInfringement: {infringement}\nDecision: {text['Decision']}"
        )
        reason_pieces = _pieces(text.get("Reason", ""))
        body = "\n".join(f"{name}: {value}" for name, value in text.items() if value)
    else:  # not the usual form (a decision on a whole session, a correction): the text as it is
        body = "\n".join(lines[: next((i for i, line in enumerate(lines) if _END.search(line)), len(lines))])
        summary, reason_pieces = None, _pieces(body)

    chunks = []
    if summary:
        chunks.append(Chunk("summary", summary[: MAX_CHUNK_CHARS + 400], "decision", {"part": "summary"}))
    for index, piece in enumerate(reason_pieces, start=1):
        label = "Reason" if summary else "Text"
        chunks.append(
            Chunk(f"reason#{index}", f"{context} ({title}). {label}: {piece}", "decision", {"part": "reason"})
        )
    if not chunks:
        raise ValueError(f"{file_name}: no text extracted")
    return Document(
        doc_id=f"decision-{season}-{hashlib.sha1(file_name.encode()).hexdigest()[:12]}",
        chunks=chunks,
        parents=[Parent("decision", f"{context}: {title}\n{body}")],
        metadata=metadata,
    )


def cited_articles(text: str) -> list[str]:
    """`Article 12.2.1 i) of the FIA International Sporting Code` -> `12.2.1 i) (International Sporting Code)`."""
    cited = []
    for match in _ARTICLE.finditer(text):
        article = match[1] + (f" {match[2]})" if match[2] else "")
        following = text[match.end() : match.end() + 90]
        if "International Sporting Code" in following:
            article += " (International Sporting Code)"
        elif "Sporting Regulations" in following:
            article += " (Sporting Regulations)"
        cited.append(article)
    return sorted(set(cited))


def _pieces(text: str) -> list[str]:
    pieces = [""]
    for sentence in re.split(r"(?<=[.;])\s+", text.strip()):
        if pieces[-1] and len(pieces[-1]) + len(sentence) + 1 > MAX_CHUNK_CHARS:
            pieces.append("")
        pieces[-1] = f"{pieces[-1]} {sentence}".strip()
    return [piece for piece in pieces if piece]


def _title(file_name: str) -> str:
    """`2025_italian_grand_prix_-_infringement_-_car_14_-_x.pdf` -> `Infringement - Car 14 - X`."""
    stem = re.sub(r"\.pdf$", "", file_name)
    parts = stem.split("_-_")[1:] or [stem]
    return " - ".join(part.replace("_", " ").strip().capitalize() for part in parts)


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d %B %Y").date().isoformat()
    except ValueError:
        return None
