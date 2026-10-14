"""The F1 evaluation dataset: computed cases from the lake and the tools, plus the cases written once and kept in
`evals/datasets/handwritten/`. `just eval-dataset` builds `evals/datasets/dev.jsonl` and `test.jsonl`."""

# The Grands Prix in French, as an analyst names them in a question.
GRAND_PRIX_FR = {
    "Abu Dhabi Grand Prix": "Grand Prix d'Abou Dabi",
    "Australian Grand Prix": "Grand Prix d'Australie",
    "Austrian Grand Prix": "Grand Prix d'Autriche",
    "Azerbaijan Grand Prix": "Grand Prix d'Azerbaïdjan",
    "Bahrain Grand Prix": "Grand Prix de Bahreïn",
    "Barcelona Grand Prix": "Grand Prix de Barcelone",
    "Belgian Grand Prix": "Grand Prix de Belgique",
    "British Grand Prix": "Grand Prix de Grande-Bretagne",
    "Canadian Grand Prix": "Grand Prix du Canada",
    "Chinese Grand Prix": "Grand Prix de Chine",
    "Dutch Grand Prix": "Grand Prix des Pays-Bas",
    "Emilia Romagna Grand Prix": "Grand Prix d'Émilie-Romagne",
    "Hungarian Grand Prix": "Grand Prix de Hongrie",
    "Italian Grand Prix": "Grand Prix d'Italie",
    "Japanese Grand Prix": "Grand Prix du Japon",
    "Las Vegas Grand Prix": "Grand Prix de Las Vegas",
    "Mexico City Grand Prix": "Grand Prix de Mexico",
    "Miami Grand Prix": "Grand Prix de Miami",
    "Monaco Grand Prix": "Grand Prix de Monaco",
    "Qatar Grand Prix": "Grand Prix du Qatar",
    "Saudi Arabian Grand Prix": "Grand Prix d'Arabie saoudite",
    "Singapore Grand Prix": "Grand Prix de Singapour",
    "Spanish Grand Prix": "Grand Prix d'Espagne",
    "São Paulo Grand Prix": "Grand Prix de São Paulo",
    "United States Grand Prix": "Grand Prix des États-Unis",
}

COMPOUNDS_FR = {
    "SOFT": "tendres",
    "MEDIUM": "mediums",
    "HARD": "durs",
    "INTERMEDIATE": "intermédiaires",
    "WET": "pluie",
}


def grand_prix(event: str, season: int) -> str:
    """The Grand Prix as a French question names it: Grand Prix d'Italie 2025."""
    return f"{GRAND_PRIX_FR.get(event, event)} {season}"
