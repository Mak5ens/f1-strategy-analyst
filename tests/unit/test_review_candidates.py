from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.evals.dataset import read_cases
from f1.evals.review import candidates, export

T0 = datetime(2026, 10, 16, tzinfo=UTC)
SUBJECT = {"season": 2025, "round": 16, "event": "Italian Grand Prix", "kind": "team", "teams": ["Ferrari"]}


def decision(point: str, action: str, reason: str | None, minutes: int = 0, after: str | None = None) -> dict[str, Any]:
    return {"thread_id": "45e195c6-d8ef", "point": point, "action": action, "reason": reason, "decided_by": "analyste",
            "text_before": f"Texte de {point}", "text_after": after, "decided_at": T0 + timedelta(minutes=minutes),
            "request": "Débrief de Monza pour Ferrari", "subject": SUBJECT}  # fmt: skip


def test_a_wrong_number_or_source_becomes_a_case_to_complete(tmp_path: Path) -> None:
    decisions = [
        decision("P1", "approve", None),
        decision("P2", "reject", "wrong_number"),
        decision("P3", "correct", "wrong_source", after="Texte juste."),
        decision("P4", "correct", "wording", after="Mieux dit."),  # wording: the agent was right
        decision("P2", "reject", "wrong_number", minutes=5),  # reviewed again: one case
    ]

    cases = candidates(decisions)

    assert [(case.id, case.family) for case in cases] == [
        ("review-45e195c6-P2", "strategy"),
        ("review-45e195c6-P3", "regulation"),
    ]
    assert cases[0].question.startswith("Débrief du Grand Prix d'Italie 2025 (« Débrief de Monza pour Ferrari »)")
    assert cases[1].answer == "Texte juste." and not cases[1].origin.reviewed
    assert cases[1].origin.inputs["agent_text"] == "Texte de P3"
    assert export(decisions, tmp_path / "review.jsonl") == 2
    assert [case.id for case in read_cases(tmp_path / "review.jsonl")] == [case.id for case in cases]
