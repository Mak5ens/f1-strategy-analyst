"""What the retrieval pipeline needs to know about the FIA corpus: filters, prompts, and how a source is cited.

Filters are hard: a question about 2025 is only searched in 2025 documents. Code reads them in the question, never
the model: a year, a relative season ("la saison dernière"), a Grand Prix named in French, an article number. A
small model asked for filters copied the example of its prompt ("Italian Grand Prix") into a question about no race.
"""

import re
import unicodedata
from collections.abc import Collection, Mapping
from datetime import date
from typing import Any

from qdrant_client import models

from core.retrieval.pipeline import Scope

REGULATIONS, DECISIONS = "sporting_regulations", "stewards_decision"

_YEAR = re.compile(r"\b(20[0-3]\d)\b")
_THIS_SEASON = re.compile(r"\b(?:cette (?:saison|annee)|saison en cours)\b")
_LAST_SEASON = re.compile(
    r"\b(?:(?:la )?saison (?:derniere|precedente|passee)|l.(?:an|annee) (?:dernier|derniere|passee?))\b"
)
# "article 55", "art. 54.4", "l'article B5.13.1", "alinéa 55.14"; or a 2026 number on its own ("B5.13").
_REFERENCE = re.compile(
    r"\b(?:articles?|art\.?|alin[ée]as?|paragraphes?)\s+(?P<number>[A-F]?\d{1,3}(?:\.\d{1,3}){0,3})\b"
    r"|\b(?P<sectioned>[A-F]\d{1,2}(?:\.\d{1,3}){1,3})\b",
    re.IGNORECASE,
)
# French names of the Grands Prix, their countries and circuits, without accents, -> names in the corpus.
GRAND_PRIX_NAMES: dict[str, tuple[str, ...]] = {
    "Bahrain Grand Prix": ("bahrein", "bahrain", "sakhir"),
    "Saudi Arabian Grand Prix": ("arabie saoudite", "saoudien", "djeddah", "jeddah"),
    "Australian Grand Prix": ("australie", "australien", "melbourne"),
    "Japanese Grand Prix": ("japon", "japonais", "suzuka"),
    "Chinese Grand Prix": ("chine", "chinois", "shanghai"),
    "Miami Grand Prix": ("miami",),
    "Emilia Romagna Grand Prix": ("emilie-romagne", "emilie romagne", "imola"),
    "Monaco Grand Prix": ("monaco",),
    "Canadian Grand Prix": ("canada", "canadien", "montreal"),
    "Spanish Grand Prix": ("espagne", "espagnol", "madrid", "barcelone"),
    "Barcelona-Catalunya Grand Prix": ("barcelone", "catalogne"),
    "Austrian Grand Prix": ("autriche", "autrichien", "spielberg", "red bull ring"),
    "British Grand Prix": ("grande-bretagne", "britannique", "silverstone"),
    "Hungarian Grand Prix": ("hongrie", "hongrois", "hungaroring", "budapest"),
    "Belgian Grand Prix": ("belgique", "belge", "spa-francorchamps", "spa"),
    "Dutch Grand Prix": ("pays-bas", "neerlandais", "zandvoort"),
    "Italian Grand Prix": ("italie", "italien", "monza"),
    "Azerbaijan Grand Prix": ("azerbaidjan", "bakou"),
    "Singapore Grand Prix": ("singapour",),
    "United States Grand Prix": ("etats-unis", "austin", "cota"),
    "Mexico City Grand Prix": ("mexique", "mexico"),
    "São Paulo Grand Prix": ("sao paulo", "bresil", "bresilien", "interlagos"),
    "Las Vegas Grand Prix": ("las vegas",),
    "Qatar Grand Prix": ("qatar", "lusail"),
    "Abu Dhabi Grand Prix": ("abu dhabi", "abou dabi", "yas marina"),
}

REWRITE = """You prepare the search of a question about Formula 1 rules, asked in French by a strategy analyst.

The corpus is in English: the FIA Formula 1 Sporting Regulations, and the decisions of the stewards at each Grand
Prix (penalties, investigations).

Return:
- "query": the question as a standalone search query, in English, with the words of the regulations
  (safety car, virtual safety car, time penalty, pit lane, unsafe release, parc ferme, tyres...); the regulations
  say "suspended" for a red flag, "lapped cars" for backmarkers, "power unit" for an engine;
- "variants": two other English wordings of the same query.
Keep the names, numbers and years of the question. Never answer the question itself. A question about anything
else than Formula 1 stays about that subject: translate it, never turn it into a Formula 1 question."""

ANSWER = """Write each claim in French, for a strategy analyst of a Formula 1 team. Keep the usual English terms
of the paddock (safety car, VSC, pit lane, DRS, parc fermé). Copy numbers, durations and article numbers exactly
as the sources give them, and name the article a rule comes from."""


class FiaProfile:
    """Profile of the FIA corpus for `core.retrieval.pipeline.RetrievalPipeline`."""

    def __init__(self, seasons: Collection[int], grands_prix: Collection[str], *, today: date | None = None) -> None:
        if not seasons:
            raise ValueError("the FIA index holds no season: run `just corpus` first")
        self.seasons = sorted(seasons)
        indexed = set(grands_prix)
        self._grands_prix = [
            (re.compile(rf"\b{re.escape(alias)}\b"), name)
            for name, aliases in GRAND_PRIX_NAMES.items()
            if name in indexed
            for alias in aliases
        ]
        self._today = today or date.today()

    @property
    def rewrite_instructions(self) -> str:
        return REWRITE

    @property
    def answer_instructions(self) -> str:
        return ANSWER

    def scope(self, question: str) -> Scope:
        text = _plain(question)
        notes: list[str] = []
        years = sorted({int(year) for year in _YEAR.findall(text)})
        if not years and _LAST_SEASON.search(text):
            years = [self._today.year - 1]
        elif not years and _THIS_SEASON.search(text):
            years = [self._today.year]
        if not years:
            years = [self.seasons[-1]]
            notes.append(f"La question ne précise pas de saison : réponse selon le règlement {years[0]}.")
        filters: dict[str, Any] = {"season": years}
        if grands_prix := sorted({name for pattern, name in self._grands_prix if pattern.search(text)}):
            filters["grand_prix"] = grands_prix
        references = [(match["number"] or match["sectioned"]).upper() for match in _REFERENCE.finditer(question)]
        return Scope(filters, list(dict.fromkeys(references)), notes)

    def search_filter(self, scope: Scope) -> models.Filter:
        """The season always. A question naming a Grand Prix gets its stewards' decisions and the regulations
        that explain them, not the decisions of other races."""
        season = models.FieldCondition(key="season", match=models.MatchAny(any=list(scope.filters["season"])))
        if not (grands_prix := scope.filters.get("grand_prix")):
            return models.Filter(must=[season])
        return models.Filter(
            must=[season],
            should=[
                models.FieldCondition(key="doc_type", match=models.MatchValue(value=REGULATIONS)),
                models.FieldCondition(key="grand_prix", match=models.MatchAny(any=list(grands_prix))),
            ],
        )

    def reference_filter(self, reference: str, scope: Scope) -> models.Filter:
        """The paragraph referenced ("55.1"), or every paragraph of the article ("55"), in the regulations of
        the season."""
        return models.Filter(
            must=[
                models.FieldCondition(key="season", match=models.MatchAny(any=list(scope.filters["season"]))),
                models.FieldCondition(key="doc_type", match=models.MatchValue(value=REGULATIONS)),
            ],
            should=[
                models.FieldCondition(key="article", match=models.MatchValue(value=reference)),
                models.FieldCondition(key="parent_article", match=models.MatchValue(value=reference)),
            ],
        )

    def label(self, payload: Mapping[str, Any]) -> str:
        if payload.get("doc_type") == DECISIONS:
            return (
                f"Décision des commissaires, {payload.get('grand_prix')} {payload.get('season')} : "
                f"{payload.get('document_title')}"
            )
        article = payload.get("parent_article") or payload.get("article")
        title = f" ({payload['title']})" if payload.get("title") else ""
        return f"Règlement sportif F1 {payload.get('season')}, article {article}{title}"


def _plain(text: str) -> str:
    """Lower case, no accents, typographic apostrophes (U+2019) made plain: "l'année dernière" -> "l'annee derniere"."""
    decomposed = unicodedata.normalize("NFKD", text.replace("\u2019", "'").casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))
