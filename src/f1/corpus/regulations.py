"""Sporting regulations PDF -> parent/child chunks, following the structure of the text, never a fixed size.

Two layouts:
- 2024 and 2025: articles `55) SAFETY CAR`, paragraphs `55.1`, `55.2`... The parent is the article.
- 2026 (Section B): articles `ARTICLE B5: ...`, titled sections `B5.13 Safety Car (SC)`, paragraphs `B5.13.1`...
  The parent is the section: an article of 2026 spans up to 25 pages, too much context for one answer.

A child is a paragraph, the unit of search. A paragraph longer than MAX_CHUNK_CHARS is split at its lettered
items (a), b)...), then at sentences. Each child's text starts with where it comes from ("2025 Sporting
Regulations, Article 55.1, Safety car"), which helps both the search and the reader of a citation.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from core.retrieval.index import Chunk, Document, Parent

# The `embed` model reads 512 tokens at most: about 1,500 characters of English, header included.
MAX_CHUNK_CHARS = 1400
# Context sent to the model for one hit: a longer article is cut into groups of consecutive paragraphs.
MAX_PARENT_CHARS = 8000
# A line found on most pages is a running header or footer.
BOILERPLATE_SHARE = 0.6


@dataclass(frozen=True)
class Layout:
    parent: re.Pattern[str]  # heading of a parent unit: groups (number, title)
    paragraph: re.Pattern[str]  # first line of a paragraph: groups (number, text)
    article: re.Pattern[str] | None = None  # 2026: article headings above the parents, for their titles


LAYOUT_2024 = Layout(
    parent=re.compile(r"^(\d{1,2})\)\s+([A-ZÀ-Ý][^a-z]*)$"),  # no lower case: "60) POST RACE PARC FERMÉ"
    paragraph=re.compile(r"^(\d{1,2}\.\d{1,2})\s+(\S.*)$"),
)
LAYOUT_2026 = Layout(
    parent=re.compile(r"^(B\d{1,2}\.\d{1,2})\s+([A-Z][^.]*?)$"),
    paragraph=re.compile(r"^(B\d{1,2}\.\d{1,2}\.\d{1,2})\s+(\S.*)$"),
    article=re.compile(r"^ARTICLE\s+(B\d{1,2}):\s*(.+)$"),
)
_TOC_ENTRY = re.compile(r"\s\d{1,3}$")  # a contents line ends with its page number
# The appendices (entry form, fees, podium ceremony...) follow the last article: no race rules there.
_APPENDICES = re.compile(r"^APPENDIX\s+1\b")


@dataclass
class _Paragraph:
    number: str
    page: int
    lines: list[str] = field(default_factory=list)


@dataclass
class _Unit:
    number: str
    title: str
    page: int
    article_title: str | None
    intro: list[str] = field(default_factory=list)
    paragraphs: list[_Paragraph] = field(default_factory=list)


def parse_regulations(pages: Sequence[str], *, season: int, issue: int, published: str, url: str) -> Document:
    layout = LAYOUT_2026 if season >= 2026 else LAYOUT_2024
    title = f"{season} Formula 1 Sporting Regulations"
    units = _units(_clean_pages(pages), layout)
    if not units:
        raise ValueError(f"No article found in the {title}: has the layout changed?")

    parents, chunks = [], []
    for unit in units:
        title_text = _title_case(unit.title)
        sources = [(unit.number, unit.page, unit.intro)] if unit.intro else []
        sources += [(p.number, p.page, [p.number + " " + p.lines[0], *p.lines[1:]]) for p in unit.paragraphs]
        # Each paragraph cut into pieces small enough to embed; the key says which paragraph and which piece.
        pieces: list[_Piece] = []
        for number, page, lines in sources:
            split = _split(lines)
            for index, text in enumerate(split, start=1):
                key = f"{unit.number}#intro" if number == unit.number else number
                pieces.append(_Piece(f"{key}#{index}" if len(split) > 1 else key, number, page, text))
        if not pieces:
            continue  # "29) VOID": an article number kept free, no text
        groups = _group(pieces)
        for group_index, group in enumerate(groups, start=1):
            parent_key = unit.number if len(groups) == 1 else f"{unit.number}~{group_index}"
            part = "" if len(groups) == 1 else f" ({group_index}/{len(groups)})"
            body = "\n".join(piece.text for piece in group)
            parent_metadata = {"article": unit.number, "title": title_text, "page": group[0].page}
            if unit.article_title:
                parent_metadata["article_title"] = unit.article_title
            parents.append(Parent(parent_key, f"{unit.number} {unit.title.strip()}{part}\n{body}", parent_metadata))
            for piece in group:
                chunks.append(
                    Chunk(
                        piece.key,
                        f"{title}, Article {piece.number}, {title_text}:\n{piece.text}",
                        parent_key,
                        {
                            "article": piece.number,
                            "parent_article": unit.number,
                            "title": title_text,
                            "page": piece.page,
                        },
                    )
                )
    return Document(
        doc_id=f"sporting-regulations-{season}",
        chunks=chunks,
        parents=parents,
        metadata={
            "doc_type": "sporting_regulations",
            "season": season,
            "document_title": title,
            "issue": issue,
            "published": published,
            "url": url,
        },
    )


def _clean_pages(pages: Sequence[str]) -> list[tuple[int, str]]:
    """Lines with their page number, without running headers, footers and page numbers."""
    split = [
        [clean for line in page.splitlines() if (clean := unicodedata.normalize("NFKC", line).strip())]
        for page in pages
    ]  # NFKC: non-breaking spaces become plain spaces
    shapes = Counter(shape for lines in split for shape in {re.sub(r"\d+", "#", line) for line in lines})
    boilerplate = {shape for shape, count in shapes.items() if count >= BOILERPLATE_SHARE * len(pages)}
    return [
        (number, line)
        for number, lines in enumerate(split, start=1)
        for line in lines
        if re.sub(r"\d+", "#", line) not in boilerplate
    ]


def _units(lines: list[tuple[int, str]], layout: Layout) -> list[_Unit]:
    units: list[_Unit] = []
    article_title: str | None = None
    for page, line in lines:
        if units and _APPENDICES.match(line):
            break
        if layout.article and (match := layout.article.match(line)):
            if not _TOC_ENTRY.search(line):
                article_title = _title_case(match[2])
            continue
        if (match := layout.parent.match(line)) and not _TOC_ENTRY.search(line) and _follows(units, match[1]):
            units.append(_Unit(match[1], match[2], page, article_title))
            continue
        if not units:
            continue  # cover page and contents
        unit = units[-1]
        match = layout.paragraph.match(line)
        if match and match[1].rsplit(".", 1)[0] == unit.number and _after(unit, match[1]):
            unit.paragraphs.append(_Paragraph(match[1], page, [match[2]]))
        elif unit.paragraphs:
            unit.paragraphs[-1].lines.append(line)
        else:
            unit.intro.append(line)
    return units


@dataclass(frozen=True)
class _Piece:
    key: str
    number: str  # paragraph number, e.g. 55.1
    page: int
    text: str


def _group(pieces: list[_Piece]) -> list[list[_Piece]]:
    """Consecutive pieces, cut where a group would exceed MAX_PARENT_CHARS."""
    groups: list[list[_Piece]] = [[]]
    size = 0
    for piece in pieces:
        if groups[-1] and size + len(piece.text) > MAX_PARENT_CHARS:
            groups.append([])
            size = 0
        groups[-1].append(piece)
        size += len(piece.text) + 1
    return groups


def _after(unit: _Unit, number: str) -> bool:
    """Paragraph numbers go up: a line of text that starts with one ("10.1 which...") is not a new paragraph."""
    return not unit.paragraphs or _sort_key(number) > _sort_key(unit.paragraphs[-1].number)


def _follows(units: list[_Unit], number: str) -> bool:
    """A real heading moves forward: this rejects numbers that only look like one (a table cell, a cross-reference)."""
    if not units:
        return True
    return _sort_key(number) > _sort_key(units[-1].number)


def _sort_key(number: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", number))


_ITEM = re.compile(r"^(?:[a-z]\)|[ivx]+\)|[a-z]\.)\s")


def _split(lines: list[str]) -> list[str]:
    text = "\n".join(lines)
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    blocks: list[list[str]] = [[]]
    for line in lines:
        if _ITEM.match(line) and blocks[-1]:
            blocks.append([])
        blocks[-1].append(line)
    pieces: list[str] = []
    for block in ("\n".join(block) for block in blocks):
        if pieces and len(pieces[-1]) + len(block) + 1 <= MAX_CHUNK_CHARS:
            pieces[-1] += "\n" + block
        elif len(block) <= MAX_CHUNK_CHARS:
            pieces.append(block)
        else:
            pieces.extend(_split_sentences(block))
    return pieces


def _split_sentences(text: str) -> list[str]:
    pieces = [""]
    for sentence in re.split(r"(?<=[.;:])\s+", text):
        if pieces[-1] and len(pieces[-1]) + len(sentence) + 1 > MAX_CHUNK_CHARS:
            pieces.append("")
        pieces[-1] = f"{pieces[-1]} {sentence}".strip()
    return [piece[i : i + MAX_CHUNK_CHARS] for piece in pieces for i in range(0, len(piece), MAX_CHUNK_CHARS)]


def _title_case(title: str) -> str:
    """`SAFETY CAR` -> `Safety car`; titles already in mixed case are kept."""
    title = " ".join(title.split())
    return title.capitalize() if title.isupper() else title
