"""How much of the agent's debriefs the analyst accepts as written (LAB-154), from the review's journal (LAB-152).

A point is accepted when the analyst approved it as it was. A correction or a rejection carries its reason, grouped
here in the four kinds of error the agent can make, and the two that are not errors of the agent's facts:

| Reason | Kind of error |
| -- | -- |
| `wrong_number` | number |
| `wrong_meaning` | interpretation: right numbers, wrong meaning |
| `wrong_source` | rules |
| `wording` | style |
| `off_topic`, `other` | other |

Only the latest decision of a point counts. The end-to-end test reviews debriefs too ("Point corrigé par le test
de bout en bout"): its requests are left out, as anything that is not a person's review.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

KINDS = {
    "wrong_number": "chiffre",
    "wrong_meaning": "interprétation",
    "wrong_source": "règlement",
    "wording": "style",
    "off_topic": "autre",
    "other": "autre",
}
E2E_MARKER = "test de bout en bout"


def part(point: str) -> str:
    """The part of the debrief a point is: S the summary, T the takeaway, P1... the moments (A1... an answer)."""
    return {"S": "summary", "T": "takeaway"}.get(point, "point")


@dataclass
class Acceptance:
    decisions: list[Mapping[str, Any]] = field(default_factory=list)

    @property
    def debriefs(self) -> int:
        return len({decision["thread_id"] for decision in self.decisions})

    def rate(self, rows: Sequence[Mapping[str, Any]] | None = None) -> float:
        rows = self.decisions if rows is None else rows
        return sum(row["action"] == "approve" for row in rows) / len(rows) if rows else 0.0

    def by(self, key: str) -> dict[str, list[Mapping[str, Any]]]:
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for row in self.decisions:
            value = part(row["point"]) if key == "part" else str(row.get(key) or "-")
            groups.setdefault(value, []).append(row)
        return groups

    @property
    def errors(self) -> Counter[str]:
        return Counter(
            KINDS.get(row["reason"] or "other", "autre") for row in self.decisions if row["action"] != "approve"
        )

    def markdown(self) -> str:
        lines = [
            f"{self.debriefs} debriefs reviewed, {len(self.decisions)} points: "
            f"**{self.rate():.0%} accepted as written**.",
            "",
            "| Points | Count | Accepted as written |",
            "| -- | --: | --: |",
        ]
        for title, key in (("checked by code", "point_status"), ("part", "part")):
            for value, rows in sorted(self.by(key).items()):
                lines.append(f"| {title}: {value} | {len(rows)} | {self.rate(rows):.0%} |")
        if self.errors:
            lines += ["", "| Kind of error | Points |", "| -- | --: |"]
            lines += [f"| {kind} | {count} |" for kind, count in self.errors.most_common()]
            lines += ["", "Corrected or rejected:", ""]
            for row in self.decisions:
                if row["action"] != "approve":
                    after = f" → « {row['text_after']} »" if row.get("text_after") else " (rejeté)"
                    lines.append(f"- `{row['thread_id'][:8]} {row['point']}` {KINDS.get(row['reason'] or 'other')}: "
                                 f"« {row['text_before']} »{after}")  # fmt: skip
        return "\n".join(lines)


def acceptance(
    decisions: Iterable[Mapping[str, Any]], *, prepared: bool = False, since: datetime | None = None
) -> Acceptance:
    """The latest decision of each point, the end-to-end test's requests left out; only the prepared debriefs
    (LAB-204) with `prepared`, only the decisions after `since`."""
    rows = sorted(decisions, key=lambda row: row["decided_at"])
    tests = {row["thread_id"] for row in rows if E2E_MARKER in (row.get("text_after") or "")}
    latest: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        if row["thread_id"] in tests or (since and row["decided_at"] < since):
            continue
        if prepared and not (row.get("subject") or {}).get("prepared"):
            continue
        latest[(row["thread_id"], row["point"])] = row
    return Acceptance(list(latest.values()))
