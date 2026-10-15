"""Candidate cases from the reviews (LAB-152): a point the analyst rejected or corrected for a wrong number or a wrong
source is a case the agent failed, worth keeping.

`just eval-dataset review-candidates` writes them to `evals/datasets/candidates/review.jsonl`, outside the folders the
dataset is built from: a person completes each one (the expected answer, the tolerance, the sources), marks it
reviewed and moves it to `handwritten/`.
"""

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core.evals.dataset import Case, Family, Origin, write_cases
from f1.display import grand_prix_fr

OUTPUT = Path("evals/datasets/candidates/review.jsonl")
# What the analyst's reason says the agent got wrong, and the family of case that measures it.
FAMILY_OF_REASON: dict[str, Family] = {"wrong_number": "strategy", "wrong_source": "regulation"}


def candidates(decisions: Iterable[Mapping[str, Any]]) -> list[Case]:
    """One case per correction or rejection for a wrong number or source, the latest decision of a point kept."""
    cases: dict[str, Case] = {}
    for decision in sorted(decisions, key=lambda row: row["decided_at"]):
        family = FAMILY_OF_REASON.get(decision["reason"] or "")
        if decision["action"] == "approve" or family is None:
            continue
        subject = decision["subject"]
        race = (
            f"du {grand_prix_fr(subject['event'])} {subject['season']}"
            if subject.get("event") and subject.get("season")
            else "de la course"
        )
        case_id = f"review-{decision['thread_id'][:8]}-{decision['point']}"
        cases[case_id] = Case(
            id=case_id,
            family=family,
            question=f"Débrief {race} (« {decision['request']} ») : ce point est-il juste ? "
            f"« {decision['text_before']} »",
            answer=decision["text_after"],
            origin=Origin(
                method="handwritten",
                by=decision["decided_by"],
                inputs={
                    "debrief": decision["thread_id"],
                    "point": decision["point"],
                    "action": decision["action"],
                    "reason": decision["reason"],
                    "agent_text": decision["text_before"],
                },
                reviewed=False,
            ),
            tags=["review-candidate", decision["reason"]],
        )
    return list(cases.values())


def export(decisions: Iterable[Mapping[str, Any]], path: Path = OUTPUT) -> int:
    cases = candidates(decisions)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_cases(path, cases)
    return len(cases)
