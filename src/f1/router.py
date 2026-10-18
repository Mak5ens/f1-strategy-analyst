"""The free question of the home page (LAB-206): code sends it down the right path, the analyst never picks a tool.

    question -> debrief (the agent: plan, review, publication)
             -> rules   (the retrieval pipeline: a sourced answer in seconds)
             -> data    (the questions of LAB-205 on the race it names: a direct answer, every number checked)
             -> None    (both or neither: the analyst chooses, the code never guesses)

Code reads the words of each path, as the retrieval pipeline reads its filters: a model asked to classify would be
one more step to trust, to pay for and to evaluate. A debrief is asked for by name. The rules have their own words
(règlement, autorisé, peut-on...), and the race data theirs (combien, écart, pole...). A question with both, about
a race it names ("Leclerc avait-il le droit de s'arrêter au tour 20 à Monza ?"), is left to the analyst.
`just eval routing` measures the routing on every case of the dataset (docs/evaluation.md).
"""

import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Literal

from f1.rag.profile import GRAND_PRIX_NAMES

Route = Literal["debrief", "rules", "data"]

_YEAR = re.compile(r"\b(20[0-3]\d)\b")
_THIS_SEASON = re.compile(r"\b(?:cette (?:saison|annee)|saison en cours)\b")
_LAST_SEASON = re.compile(
    r"\b(?:(?:la )?saison (?:derniere|precedente|passee)|l.(?:an|annee) (?:dernier|derniere|passee?))\b"
)
# Every way a text may name a Grand Prix: its French names, places and countries, and its English name.
_GRANDS_PRIX = [
    (re.compile(rf"\b{re.escape(alias)}\b"), name)
    for name, aliases in GRAND_PRIX_NAMES.items()
    for alias in (*aliases, name.lower().removesuffix(" grand prix"))
]

# The words of each path, on the text without accents nor capitals.
_DEBRIEF = re.compile(r"\b(?:debrief\w*|bilan strategique|analyse strategique|resume strategique)\b")
# What only the rules answer: what is allowed, what a rule or the stewards say.
_RULES = re.compile(
    r"\b(?:reglement\w*|regles?|articles?|art\.|alineas?|autoris\w*|interdi\w*|permis|droit|peut-on|"
    r"oblig\w*|procedures?|exigences?|commissaires|decisions?|que se passe-t-il|que risque|consequences?|"
    r"exceptions?|responsabilites?)\b"
)
# A sanction is the stewards': "pourquoi a-t-il été pénalisé" asks for their decision, not for the data.
_SANCTIONS = re.compile(r"\b(?:penali\w*|sanction\w*|amendes?|purg\w*)\b")
# What the data of a race answers: a number, a position, a duel.
_DATA = re.compile(
    r"(?:^|[,:] )qui (?:a|d)\b"  # "Qui a gagné", not "la voiture 5 qui a dépassé"
    r"|\b(?:combien|ecart|quel pilote|pole|meilleur tour|parti|termine|position|place|degradation|relais|"
    r"arrets?|tours? \d+|pneus|vainqueur|remporte|gagne|podium|classement|sorti devant|en quel temps|"
    r"undercut|overcut)\b"
)
_WHY = re.compile(r"\bpourquoi\b")


@dataclass(frozen=True)
class Routing:
    route: Route | None  # None: the analyst chooses
    seasons: list[int] = field(default_factory=list)
    grands_prix: list[str] = field(default_factory=list)
    named: list[str] = field(default_factory=list)  # the drivers and teams it names, as the data writes them
    reason: str = ""  # why this path, or why the analyst is asked


class Router:
    """Routes the questions, knowing the names of the drivers and teams of the data (`GrandPrix.people`)."""

    def __init__(self, drivers: Collection[str] = (), teams: Collection[str] = (), *, today: date | None = None):
        self.today = today or date.today()
        self._names = [
            (re.compile(rf"\b{re.escape(alias)}\b"), name)
            for name, aliases in [
                *((driver, _driver_aliases(driver)) for driver in drivers),
                *((team, _team_aliases(team)) for team in teams),
            ]
            for alias in aliases
        ]

    def route(self, question: str) -> Routing:
        """Debrief when asked for; rules when nothing of a race is named; else the words of each path decide, and
        the analyst when they say both or neither."""
        seasons, grands_prix = read_race(question, self.today)
        text = plain(question)
        named = sorted({name for pattern, name in self._names if pattern.search(text)})
        found = Routing(None, seasons, grands_prix, named)
        if _DEBRIEF.search(text):
            return replace(found, route="debrief", reason="la question demande un débrief")
        if not grands_prix and not named:
            # No race, no driver, no team: a question on the rules, or on nothing the data holds. The retrieval
            # pipeline answers the first and abstains on the second.
            return replace(found, route="rules", reason="la question ne nomme ni course, ni pilote, ni écurie")
        sanction = bool(_SANCTIONS.search(text))
        rules = bool(_RULES.search(text)) or (sanction and bool(_WHY.search(text)))
        data = bool(_DATA.search(text)) or (not sanction and bool(_WHY.search(text)))
        if rules and data:
            return replace(found, reason="la question porte à la fois sur le règlement et sur les données d'une course")
        if rules or (sanction and not data):
            return replace(found, route="rules", reason="la question porte sur le règlement")
        if data:
            return replace(found, route="data", reason="la question porte sur les données d'une course")
        return replace(found, reason="rien dans la question ne dit si elle porte sur le règlement ou sur les données")


def read_race(text: str, today: date | None = None) -> tuple[list[int], list[str]]:
    """The seasons and the Grands Prix a text names, read by code."""
    text = plain(text)
    today = today or date.today()
    seasons = sorted({int(year) for year in _YEAR.findall(text)})
    if not seasons and _LAST_SEASON.search(text):
        seasons = [today.year - 1]
    elif not seasons and _THIS_SEASON.search(text):
        seasons = [today.year]
    return seasons, sorted({name for pattern, name in _GRANDS_PRIX if pattern.search(text)})


def plain(text: str) -> str:
    """Lower case, no accents, typographic apostrophes (U+2019) made plain: "l'année dernière" -> "l'annee derniere"."""
    decomposed = unicodedata.normalize("NFKD", text.replace("\u2019", "'").casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _driver_aliases(name: str) -> list[str]:
    """ "Lando Norris": "lando norris" and "norris"; a short last name ("Zhou") only in full."""
    full = plain(name)
    last = full.split()[-1]
    return [full, last] if len(last) >= 4 else [full]


def _team_aliases(name: str) -> list[str]:
    """ "Red Bull Racing": "red bull racing" and "red bull"; "Haas F1 Team": "haas"; "RB" is too short a word."""
    full = plain(name)
    short = re.sub(r"^kick |(?: f1 team| racing)$", "", full)
    return [alias for alias in dict.fromkeys([full, short]) if len(alias) >= 4]
