"""The router of the home page's free question (LAB-206): code, measured on the dataset as `just eval routing` does."""

from datetime import date
from pathlib import Path

import pytest

from core.evals.dataset import read_cases
from f1.evals.routing import TARGET, measure
from f1.router import Router, read_race

DATASETS = Path(__file__).parents[2] / "evals" / "datasets"
# The drivers and teams of the 2024 to 2026 grids, as the lake writes them (`GrandPrix.people`).
DRIVERS = [
    "Alexander Albon", "Andrea Kimi Antonelli", "Arvid Lindblad", "Carlos Sainz", "Charles Leclerc",
    "Daniel Ricciardo", "Esteban Ocon", "Fernando Alonso", "Franco Colapinto", "Gabriel Bortoleto",
    "George Russell", "Guanyu Zhou", "Isack Hadjar", "Jack Doohan", "Kevin Magnussen", "Lance Stroll",
    "Lando Norris", "Lewis Hamilton", "Liam Lawson", "Logan Sargeant", "Max Verstappen", "Nico Hulkenberg",
    "Oliver Bearman", "Oscar Piastri", "Pierre Gasly", "Sergio Perez", "Valtteri Bottas", "Yuki Tsunoda",
]  # fmt: skip
TEAMS = ["Alpine", "Aston Martin", "Audi", "Cadillac", "Ferrari", "Haas F1 Team", "Kick Sauber", "McLaren", "Mercedes",
         "RB", "Racing Bulls", "Red Bull Racing", "Williams"]  # fmt: skip
ROUTER = Router(DRIVERS, TEAMS, today=date(2026, 10, 18))


@pytest.mark.parametrize("split", ["dev", "test"])
def test_each_family_of_the_dataset_takes_its_path(split: str) -> None:
    report = measure(read_cases(DATASETS / f"{split}.jsonl"), ROUTER)

    assert report.rate >= TARGET, report.markdown()
    assert all(m.routing.route is None for m in report.missed), report.markdown()  # asked, never sent wrong


@pytest.mark.parametrize(
    "question",
    [
        "Débrief stratégique du GP de Monaco 2025 pour Ferrari",
        "Fais-moi le debrief de la course de Norris à Monza",
        "Un bilan stratégique du dernier Grand Prix",
    ],
)
def test_a_debrief_asked_for_goes_to_the_agent(question: str) -> None:
    assert ROUTER.route(question).route == "debrief"


@pytest.mark.parametrize(
    ("question", "path"),
    [
        ("Peut-on changer de pneus sous drapeau rouge ?", "rules"),
        ("Combien de points rapporte une victoire en sprint ?", "rules"),  # nothing of a race named
        ("Pourquoi Hamilton a-t-il été pénalisé au GP de Hongrie 2025 ?", "rules"),  # the stewards' decision
        ("Combien d'arrêts Norris a-t-il faits en 2025 ?", "data"),  # a driver: the race is asked for
        ("Quel écart entre Leclerc et Russell au tour 20 à Monza 2025 ?", "data"),
        ("Qui a gagné le GP du Japon 2025 ?", "data"),
        ("Pourquoi Ferrari a-t-elle arrêté Leclerc si tôt à Monza ?", "data"),
    ],
)
def test_the_words_of_each_path(question: str, path: str) -> None:
    assert ROUTER.route(question).route == path


def test_the_rules_and_the_data_of_a_race_together_are_left_to_the_analyst() -> None:
    routing = ROUTER.route("Leclerc avait-il le droit de s'arrêter au tour 20 à Monza 2025 ?")

    assert routing.route is None and "à la fois" in routing.reason
    assert (routing.seasons, routing.grands_prix, routing.named) == (
        [2025],
        ["Italian Grand Prix"],
        ["Charles Leclerc"],
    )


def test_names_are_read_in_full_or_by_last_name_and_teams_by_their_usual_name() -> None:
    routing = ROUTER.route("Écart entre Verstappen et Lando Norris chez Red Bull et Haas à Bakou l'an dernier")

    assert routing.named == ["Haas F1 Team", "Lando Norris", "Max Verstappen", "Red Bull Racing"]
    assert (routing.seasons, routing.grands_prix) == ([2025], ["Azerbaijan Grand Prix"])
    assert ROUTER.route("Combien de points pour RB ?").named == []  # too short a word to be sure


def test_the_race_is_read_as_the_retrieval_pipeline_reads_it() -> None:
    assert read_race("GP d'Émilie-Romagne 2024 et Imola cette saison", date(2026, 1, 1)) == (
        [2024],
        ["Emilia Romagna Grand Prix"],
    )
    assert read_race("le Japon cette saison", date(2026, 1, 1)) == ([2026], ["Japanese Grand Prix"])
