"""What the FIA profile reads in a question: seasons, Grands Prix and article references, by code only."""

from datetime import date

import pytest
from qdrant_client import models

from f1.rag.profile import DECISIONS, REGULATIONS, FiaProfile

PROFILE = FiaProfile([2024, 2025, 2026], ["Italian Grand Prix", "Hungarian Grand Prix"], today=date(2026, 10, 12))


@pytest.mark.parametrize(
    ("question", "seasons"),
    [
        ("Que dit le règlement 2025 sur la VSC ?", [2025]),
        ("Entre 2024 et 2025, qu'est-ce qui a changé ?", [2024, 2025]),
        ("Quelle pénalité cette saison pour un excès de vitesse ?", [2026]),
        ("Et l\u2019année dernière, sous safety car ?", [2025]),  # typographic apostrophe
        ("Quelles règles pour la saison précédente ?", [2025]),
        ("Peut-on changer de pneus sous drapeau rouge ?", [2026]),
    ],
)
def test_seasons(question: str, seasons: list[int]) -> None:
    assert PROFILE.scope(question).filters["season"] == seasons


def test_no_season_falls_back_to_the_latest_and_says_so() -> None:
    scope = PROFILE.scope("Peut-on changer de pneus sous drapeau rouge ?")
    assert scope.notes == ["La question ne précise pas de saison : réponse selon le règlement 2026."]
    assert PROFILE.scope("En 2025, peut-on changer de pneus ?").notes == []


@pytest.mark.parametrize(
    ("question", "grands_prix"),
    [
        ("Pénalités de Monza en 2025 ?", ["Italian Grand Prix"]),
        ("Pourquoi Hamilton a-t-il été pénalisé au GP de Hongrie ?", ["Hungarian Grand Prix"]),
        ("Le Grand Prix d'Italie et le Hungaroring", ["Hungarian Grand Prix", "Italian Grand Prix"]),
        ("Que s'est-il passé à Bakou ?", []),  # not in the index given
        ("Une question sans course", []),
        ("Les spatules du parc fermé", []),  # "spa" only as a word
    ],
)
def test_grands_prix_from_french_names(question: str, grands_prix: list[str]) -> None:
    assert PROFILE.scope(question).filters.get("grand_prix", []) == grands_prix


@pytest.mark.parametrize(
    ("question", "references"),
    [
        ("Que dit l'article 55.14 ?", ["55.14"]),
        ("Selon l'art. 54 et l'alinéa 54.4", ["54", "54.4"]),
        ("Que dit B5.13.1 en 2026 ?", ["B5.13.1"]),
        ("l'article b5.13", ["B5.13"]),
        ("Une pénalité de 5 secondes à 1.5 tour de la fin", []),  # numbers, not references
    ],
)
def test_references(question: str, references: list[str]) -> None:
    assert list(PROFILE.scope(question).references) == references


def test_a_grand_prix_keeps_the_regulations_that_explain_its_decisions() -> None:
    search = PROFILE.search_filter(PROFILE.scope("Pénalités à Monza en 2025 ?"))
    assert search.should is not None
    conditions = [c for c in search.should if isinstance(c, models.FieldCondition)]
    assert {c.key for c in conditions} == {"doc_type", "grand_prix"}
    assert any(isinstance(c.match, models.MatchValue) and c.match.value == REGULATIONS for c in conditions)


def test_labels() -> None:
    regulation = {"doc_type": REGULATIONS, "season": 2025, "parent_article": "55", "title": "Safety car"}
    assert PROFILE.label(regulation) == "Règlement sportif F1 2025, article 55 (Safety car)"
    decision = {"doc_type": DECISIONS, "season": 2025, "grand_prix": "Italian Grand Prix", "document_title": "Car 5"}
    assert PROFILE.label(decision) == "Décision des commissaires, Italian Grand Prix 2025 : Car 5"
