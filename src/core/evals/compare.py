"""A run against the reference runs of the main branch, on the same cases: the gate of the evaluation CI (LAB-149).

A sample of a few cases per family cannot be held to a threshold set on the whole family: an easy draw passes, a
hard one fails. So each gated metric is compared with what the reference run scored on the very same cases, and a
change fails when it loses more than a margin: 5 points, or two of the cases compared when that is more, so that one
answer the model words differently (at temperature 0 too) fails no one.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.evals.dataset import Case

# The score of one case that each family metric averages (`harness.case_scores`).
CASE_SCORE = {"accuracy": "passed", "abstention": "passed", "safe": "passed", "grade/5": "grade"}
# The metrics not on a 0 to 1 scale: the margin is scaled with them.
SCALES = {"grade/5": 5.0}
MARGIN = 0.05
NOISE_CASES = 2

CaseScores = Mapping[str, Mapping[str, float | bool]]


@dataclass(frozen=True)
class Comparison:
    family: str
    metric: str
    reference_run: str
    cases: int  # the cases both runs scored
    value: float
    reference: float
    margin: float  # on the metric's scale

    @property
    def delta(self) -> float:
        return self.value - self.reference

    @property
    def regressed(self) -> bool:
        return self.delta < -self.margin - 1e-9


def compare(
    cases: Sequence[Case],
    scores: CaseScores,
    references: Mapping[str, tuple[str, CaseScores]],
    gated: Mapping[str, Sequence[str]],
    *,
    margin: float = MARGIN,
    noise_cases: int = NOISE_CASES,
) -> list[Comparison]:
    """One line per gated metric of each family in `cases`: the run's score and the reference's, on the cases both
    scored. `references` maps a family to its reference run and that run's case scores."""
    comparisons = []
    for family, metrics in gated.items():
        if family not in references:
            continue
        run, reference = references[family]
        ids = [case.id for case in cases if case.family == family]
        for metric in metrics:
            key = CASE_SCORE.get(metric, metric)
            pairs = [
                (float(scores[i][key]), float(reference[i][key]))
                for i in ids
                if key in scores.get(i, {}) and key in reference.get(i, {})
            ]
            if not pairs:
                continue
            comparisons.append(
                Comparison(
                    family=family,
                    metric=metric,
                    reference_run=run,
                    cases=len(pairs),
                    value=sum(value for value, _ in pairs) / len(pairs),
                    reference=sum(value for _, value in pairs) / len(pairs),
                    margin=max(margin, noise_cases / len(pairs)) * SCALES.get(metric, 1.0),
                )
            )
    return comparisons


def markdown(
    comparisons: Sequence[Comparison],
    *,
    title: str,
    other_failures: Sequence[str] = (),
    details: Sequence[str] = (),
    marker: str = "",
) -> str:
    """The report of a comparison, for a pull request comment: a verdict, a table, then what failed and by how much.
    `other_failures` are failures found otherwise (a threshold of the whole family), one sentence each."""
    failed = [c for c in comparisons if c.regressed]
    count = len(failed) + len(other_failures)
    verdict = f"**{count} check(s) failed**" if count else "**Every metric holds**"
    # The marker (an HTML comment) lets the CI find its comment again and edit it instead of adding one.
    lines = [marker] if marker else []
    lines += [
        f"### {title}",
        "",
        f"{verdict} against the reference runs of the main branch.",
        "",
        "| Family | Metric | Cases | This run | Main | Δ | Allowed drop | |",
        "| -- | -- | --: | --: | --: | --: | --: | -- |",
    ]
    for c in comparisons:
        lines.append(
            f"| {c.family} | {c.metric} | {c.cases} | {c.value:.2f} | {c.reference:.2f} | {c.delta:+.2f} "
            f"| {c.margin:.2f} | {'❌' if c.regressed else '✅'} |"
        )
    if count:
        lines.append("")
        lines += [
            f"- **{c.family}** {c.metric} fell from {c.reference:.2f} to {c.value:.2f} on the same {c.cases} cases "
            f"({c.delta:+.2f}), more than the {c.margin:.2f} allowed."
            for c in failed
        ]
        lines += [f"- {failure}" for failure in other_failures]
    if details:
        lines += ["", *details]
    return "\n".join(lines) + "\n"


def side_by_side(
    reports: Sequence[Mapping[str, Any]],
    gated: Mapping[str, Sequence[str]],
    *,
    priced: Callable[[str], bool] = lambda model: True,
) -> str:
    """Runs of several models on the same cases, one column each: the gated metric of every family, the share of
    questions answered, the latency of a question and the cost of answering. `priced` tells a model whose cost is a
    real price from one the gateway counts at an internal price (a local model: its cost is the hardware's)."""
    models = [str(report.get("model") or report["run"]) for report in reports]
    lines = [
        "| Family | Metric | " + " | ".join(f"`{model}`" for model in models) + " |",
        "| -- | -- |" + " --: |" * len(models),
    ]
    for family, metrics in gated.items():
        for metric in [*metrics, "answered"]:
            values = [report["families"].get(family, {}).get(metric) for report in reports]
            if all(value is None for value in values):
                continue
            cells = ["-" if value is None else f"{value:.2f}" for value in values]
            lines.append(f"| {family} | {metric} | " + " | ".join(cells) + " |")
    for key in ("p50", "p95"):
        cells = [f"{report['latency_s']['all'][key]:.1f} s" for report in reports]
        lines.append(f"| all | latency {key} | " + " | ".join(cells) + " |")
    cells = []
    for model, report in zip(models, reports, strict=True):
        cost, cases = report.get("system_cost_usd"), sum(f["cases"] for f in report["families"].values())
        if cost is None:
            cells.append("-")
        elif priced(model):
            cells.append(f"${cost:.2f} (${1000 * cost / cases:.2f} / 1,000 questions)")
        else:
            cells.append("local: the hardware's")
    lines.append("| all | cost of answering | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
