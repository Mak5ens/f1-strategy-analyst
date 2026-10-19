"""The share of points accepted as written (LAB-154), and the kinds of error, from a review journal written by hand."""

from datetime import UTC, datetime, timedelta
from typing import Any

from f1.evals.acceptance import acceptance
from f1.evals.agent import path_for
from f1.router import Routing

T0 = datetime(2026, 10, 18, 20, tzinfo=UTC)


def row(thread: str, point: str, action: str, reason: str | None = None, *, minutes: int = 0, status: str = "verified",
        after: str | None = None, prepared: str | None = "team") -> dict[str, Any]:  # fmt: skip
    return {"thread_id": thread, "point": point, "action": action, "reason": reason, "point_status": status,
            "text_before": f"{point} avant", "text_after": after, "decided_at": T0 + timedelta(minutes=minutes),
            "subject": {"prepared": prepared} if prepared else {}}  # fmt: skip


JOURNAL = [
    row("a", "S", "correct", "wording", after="S corrigé"),
    row("a", "S", "approve", minutes=5),  # reviewed again: the latest decision counts
    row("a", "P1", "correct", "wrong_meaning", after="P1 corrigé", status="unverified"),
    row("a", "P2", "approve"),
    row("b", "P1", "reject", "wrong_number", status="unverified", prepared=None),
    row("b", "T", "approve", prepared=None),
    row("e2e", "S", "correct", "wording", after="Point corrigé par le test de bout en bout."),
    row("e2e", "P1", "approve"),
]


def test_the_latest_decision_of_each_point_counts_and_the_end_to_end_test_does_not() -> None:
    report = acceptance(JOURNAL)

    assert (report.debriefs, len(report.decisions), report.rate()) == (2, 5, 0.6)
    assert report.errors == {"interprétation": 1, "chiffre": 1}
    assert {status: report.rate(rows) for status, rows in report.by("point_status").items()} == {
        "verified": 1.0,
        "unverified": 0.0,
    }
    assert "**60% accepted as written**" in report.markdown()


def test_the_prepared_debriefs_and_a_date_narrow_the_journal() -> None:
    assert acceptance(JOURNAL, prepared=True).debriefs == 1
    assert len(acceptance(JOURNAL, since=T0 + timedelta(minutes=1)).decisions) == 1


def test_the_evaluation_takes_the_path_an_analyst_would_choose() -> None:
    assert path_for(Routing("rules", [2025])) == "rules"
    assert path_for(Routing("debrief", [2025])) == "data"
    assert path_for(Routing(None, [], [], ["LEC"])) == "data"  # a driver named: the race's data
    assert path_for(Routing(None, [2025])) == "rules"


def test_a_failed_case_is_put_down_to_the_check_that_stopped_it() -> None:
    from core.evals.harness import Record
    from f1.evals.agent import failure_causes

    records = [
        Record("d1", "data", "?", False, "« … » : numbers that are in none of the analyses", meta={"path": "data",
                                                                                                  "race": "2025/2"}),
        Record("d2", "data", "?", False, "Sur quelle course ?", meta={"path": "data", "race": None}),
        Record("d3", "data", "?", True, "Leclerc", meta={"path": "data", "race": "2025/2"}),
        Record("s1", "strategy", "?", False, "« … » : sens, contredit : …", meta={"path": "data", "race": "2025/2"}),
        Record("s2", "strategy", "?", True, "Une bonne réponse", meta={"path": "data", "race": "2025/2"}),
    ]  # fmt: skip
    scores: dict[str, dict[str, Any]] = {
        "d1": {"passed": False},
        "d2": {"passed": False},
        "d3": {"passed": False},
        "s1": {"grade": 1.0},
        "s2": {"grade": 4.0},
    }

    table = failure_causes(records, scores)

    assert "| data | 1 | 1 | 0 | 0 | 1 |" in table
    assert "| strategy | 0 | 0 | 1 | 0 | 0 |" in table
