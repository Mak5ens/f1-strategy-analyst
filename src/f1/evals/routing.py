"""`just eval routing`: the path the home page's router (LAB-206) takes on each case of the dataset, by family.

Code routes, so this costs no call and takes a second. Each family has its path: the rules and the stewards'
decisions go to the retrieval pipeline, the numbers of a race to the questions on its data. Out of corpus and safety
cases have none: whatever the path, it must abstain or refuse, which `just eval` measures. A case the router leaves
to the analyst counts as missed: the target is 95 % on the development set, every family together.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from core.evals.dataset import Case, Family
from f1.router import Route, Router, Routing

EXPECTED: dict[Family, Route] = {
    "regulation": "rules",
    "retrieval": "rules",
    "data": "data",
    "computation": "data",
    "strategy": "data",
}
TARGET = 0.95


@dataclass(frozen=True)
class Missed:
    case: Case
    routing: Routing


@dataclass(frozen=True)
class RoutingReport:
    right: Counter[Family]
    total: Counter[Family]
    missed: list[Missed]

    @property
    def rate(self) -> float:
        return sum(self.right.values()) / max(1, sum(self.total.values()))

    def markdown(self) -> str:
        lines = ["| Family | Path | Right |", "| -- | -- | -- |"]
        for family, path in EXPECTED.items():
            if self.total[family]:
                lines.append(f"| {family} | {path} | {self.right[family]}/{self.total[family]} |")
        lines.append(f"| **all** | | **{sum(self.right.values())}/{sum(self.total.values())} ({self.rate:.1%})** |")
        lines += ["", *(f"- `{m.case.id}` -> {m.routing.route or 'asked'}: {m.case.question}" for m in self.missed)]
        return "\n".join(lines)


def measure(cases: Sequence[Case], router: Router) -> RoutingReport:
    right: Counter[Family] = Counter()
    total: Counter[Family] = Counter()
    missed = []
    for case in cases:
        if (expected := EXPECTED.get(case.family)) is None:
            continue
        routing = router.route(case.question)
        total[case.family] += 1
        if routing.route == expected:
            right[case.family] += 1
        else:
            missed.append(Missed(case, routing))
    return RoutingReport(right, total, missed)
