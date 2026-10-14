"""Which round a Grand Prix was, and who raced it: the tools take a round and driver codes, a question gives names.

A model asked for "le Grand Prix d'Italie 2025" guesses its round from memory, and wrongly (round 14, for the 16th).
This tool reads it from the lake, with the drivers' codes, names and teams.
"""

import unicodedata

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.rag.profile import GRAND_PRIX_NAMES
from f1.tools.data import RaceData


class FindRaceInput(BaseModel):
    season: int = Field(ge=2018, le=2100, description="Championship year, e.g. 2025")
    grand_prix: str = Field(
        min_length=2,
        description="The Grand Prix as named, in English or French: 'Italian Grand Prix', 'Italie', 'Monza'",
    )


class Driver(BaseModel):
    code: str = Field(description="Three-letter code the other tools take, e.g. LEC")
    name: str
    team: str | None


class FindRaceOutput(BaseModel):
    season: int
    round: int
    event: str
    location: str | None
    sessions: list[str] = Field(description="Sessions in the data: FP1-FP3, SQ, Q, S (sprint), R (race)")
    drivers: list[Driver] = Field(description="Drivers of the race, in finishing order")


def find_race(data: RaceData, request: FindRaceInput) -> FindRaceOutput:
    events = data.events(request.season)
    if not events:
        raise ToolError(f"No race of {request.season} in the data.")
    wanted = _plain(request.grand_prix)
    matches = [event for event in events if wanted in _names(event)]
    if not matches:
        names = ", ".join(sorted({str(event["event_name"]) for event in events}))
        raise ToolError(f"No Grand Prix '{request.grand_prix}' in {request.season}. Grands Prix: {names}.")
    event = matches[0]
    round_number = int(event["round"])
    return FindRaceOutput(
        season=request.season,
        round=round_number,
        event=str(event["event_name"]),
        location=event.get("location"),
        sessions=data.session_codes(request.season, round_number),
        drivers=[Driver(**driver) for driver in data.drivers(request.season, round_number)],
    )


def _names(event: dict[str, object]) -> set[str]:
    """Every way to name the event: its name with and without "Grand Prix", its place, its country, French names."""
    name = str(event["event_name"])
    names = {_plain(name), _plain(name.removesuffix(" Grand Prix"))}
    names |= {_plain(str(event[key])) for key in ("location", "country") if event.get(key)}
    names |= {_plain(alias) for alias in GRAND_PRIX_NAMES.get(name, ())}
    return names


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().strip()
    for prefix in ("grand prix d'", "grand prix de ", "grand prix du ", "grand prix des ", "gp d'", "gp de ", "gp du "):
        text = text.removeprefix(prefix)
    return text
