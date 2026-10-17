"""How the front names what the data names in English: Grands Prix in French, and the colour of each team.

The colours are the teams' livery colours as FastF1 gives them for its plots (`fastf1.plotting`), used as data to tell
teams apart, never with a logo. The lake does not store them: a team missing here gets no colour, not a guess.
"""

from pydantic import BaseModel, ConfigDict, Field

GRAND_PRIX_FR: dict[str, str] = {
    "Bahrain Grand Prix": "Grand Prix de Bahreïn",
    "Saudi Arabian Grand Prix": "Grand Prix d'Arabie saoudite",
    "Australian Grand Prix": "Grand Prix d'Australie",
    "Japanese Grand Prix": "Grand Prix du Japon",
    "Chinese Grand Prix": "Grand Prix de Chine",
    "Miami Grand Prix": "Grand Prix de Miami",
    "Emilia Romagna Grand Prix": "Grand Prix d'Émilie-Romagne",
    "Monaco Grand Prix": "Grand Prix de Monaco",
    "Canadian Grand Prix": "Grand Prix du Canada",
    "Spanish Grand Prix": "Grand Prix d'Espagne",
    "Barcelona-Catalunya Grand Prix": "Grand Prix de Barcelone-Catalogne",
    "Barcelona Grand Prix": "Grand Prix de Barcelone",
    "Austrian Grand Prix": "Grand Prix d'Autriche",
    "British Grand Prix": "Grand Prix de Grande-Bretagne",
    "Hungarian Grand Prix": "Grand Prix de Hongrie",
    "Belgian Grand Prix": "Grand Prix de Belgique",
    "Dutch Grand Prix": "Grand Prix des Pays-Bas",
    "Italian Grand Prix": "Grand Prix d'Italie",
    "Azerbaijan Grand Prix": "Grand Prix d'Azerbaïdjan",
    "Singapore Grand Prix": "Grand Prix de Singapour",
    "United States Grand Prix": "Grand Prix des États-Unis",
    "Mexico City Grand Prix": "Grand Prix de Mexico",
    "São Paulo Grand Prix": "Grand Prix de São Paulo",
    "Las Vegas Grand Prix": "Grand Prix de Las Vegas",
    "Qatar Grand Prix": "Grand Prix du Qatar",
    "Abu Dhabi Grand Prix": "Grand Prix d'Abu Dhabi",
}

TEAM_COLOURS: dict[str, str] = {
    "Alpine": "#00a1e8",
    "Aston Martin": "#229971",
    "Audi": "#ff2d00",
    "Cadillac": "#444444",
    "Ferrari": "#e8002d",
    "Haas F1 Team": "#b6babd",
    "Kick Sauber": "#52e252",
    "McLaren": "#ff8000",
    "Mercedes": "#27f4d2",
    "RB": "#6692ff",
    "Racing Bulls": "#6692ff",
    "Red Bull Racing": "#3671c6",
    "Williams": "#64c4ff",
}


def grand_prix_fr(name: str) -> str:
    return GRAND_PRIX_FR.get(name, name)


def team_colour(team: str | None) -> str | None:
    return TEAM_COLOURS.get(team) if team else None


class Response(BaseModel):
    """What the API returns: every field always present, its default included, so the generated client needs no
    `?? []`."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Driver(Response):
    code: str
    name: str
    team: str | None = None
    colour: str | None = Field(None, description="The team's colour, #rrggbb, when known")


def driver(code: str, name: str | None, team: str | None) -> Driver:
    return Driver(code=code, name=name or code, team=team, colour=team_colour(team))
