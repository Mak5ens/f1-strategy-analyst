"""The evaluation harness: run a system once on the cases, then score its recorded answers family by family.

Each family has the metric that fits it, from a standard tool where one exists:

| Family | Scored by | Metric |
| -- | -- | -- |
| data, computation | promptfoo | share of answers with the expected value (numbers within their tolerance) |
| safety | promptfoo | share that neither shows what must not appear nor answers when it must decline |
| out_of_corpus | promptfoo | share of abstentions |
| retrieval, regulation | code | Recall@5, MRR@10, nDCG@5 on the distinct sources retrieved |
| regulation | Ragas | faithfulness of the answer to its contexts, recall of the reference in the contexts |
| strategy | LLM judge | mean grade over 5 on an explicit rubric, share graded 4 or more |

The system runs once (`run_system`), and every scorer reads what it recorded, so a scorer can change without paying
the system's calls again. promptfoo and Ragas run apart (`npx`, and `evals/ragas/` with its own environment: Ragas
needs openai < 3), on files.
"""

import json
import logging
import math
import random
import statistics
import subprocess
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from core.evals.dataset import FAMILIES, Case, to_promptfoo
from core.retrieval.evaluation import matches

log = logging.getLogger("core.evals")

PROMPTFOO = "promptfoo@0.123.1"
PROMPTFOO_FAMILIES = frozenset({"data", "computation", "safety", "out_of_corpus"})
RETRIEVAL_FAMILIES = frozenset({"retrieval", "regulation", "out_of_corpus"})
ABSTENTION = "ABSTENTION"  # how a recorded answer says the system declined, for promptfoo's checks


@dataclass
class Record:
    """What a system did on one case."""

    id: str
    family: str
    question: str
    answered: bool
    answer: str
    contexts: list[str] = field(default_factory=list)  # what the model read: passages, tool results
    retrieved: list[dict[str, Any]] = field(default_factory=list)  # payloads of the passages found, in rank order
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    seconds: float = 0.0
    trace_id: str | None = None
    error: str | None = None

    @property
    def output(self) -> str:
        """The answer as promptfoo reads it."""
        if self.error:
            return f"{ABSTENTION} (error) {self.error}"
        return self.answer if self.answered else f"{ABSTENTION} {self.answer}".strip()


class System(Protocol):
    name: str

    def run(self, case: Case) -> Record: ...


def sample(cases: Sequence[Case], per_family: int | None, *, seed: int) -> list[Case]:
    """At most `per_family` cases of each family, drawn with a seed; all of them when None."""
    if per_family is None:
        return list(cases)
    rng = random.Random(seed)
    chosen: list[Case] = []
    for family in FAMILIES:
        members = [case for case in cases if case.family == family]
        chosen += rng.sample(members, min(per_family, len(members)))
    return chosen


def run_system(
    system: System,
    cases: Sequence[Case],
    *,
    workers: int = 4,
    on_record: Callable[[Record], None] = lambda record: None,
) -> list[Record]:
    """The system on every case, a few at a time: the gateway's rate limit sets the pace (its client waits out a
    429). A case that raises is recorded as an error, which every scorer counts as a failure."""

    def one(case: Case) -> Record:
        start = time.monotonic()
        try:
            record = system.run(case)
        except Exception as error:
            log.exception("%s failed", case.id)
            record = Record(case.id, case.family, case.question, False, "", error=f"{type(error).__name__}: {error}")
        record.seconds = round(time.monotonic() - start, 2)
        return record

    records: dict[str, Record] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(one, case) for case in cases]):
            record = future.result()
            records[record.id] = record
            on_record(record)
    return [records[case.id] for case in cases]


def write_records(path: Path, records: Iterable[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(asdict(record), ensure_ascii=False) + "\n" for record in records))


def read_records(path: Path) -> list[Record]:
    return [Record(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


# ---- retrieval ----------------------------------------------------------------------------------------------------


def retrieval_scores(case: Case, record: Record, *, k: int = 5) -> dict[str, float] | None:
    """Recall@k, MRR@10 and nDCG@k of the sources retrieved, counted on distinct parents, as a model reads them.
    None for a case with no expected source."""
    if not case.sources:
        return None
    parents: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for payload in record.retrieved:
        parent = str(payload.get("parent_id") or payload.get("doc_id") or len(seen))
        if parent not in seen:
            seen.add(parent)
            parents.append(payload)
    relevant = [any(matches(payload, expected) for expected in case.sources) for payload in parents]
    first = next((rank for rank, hit in enumerate(relevant[:10], start=1) if hit), None)
    gains = sum(1 / math.log2(rank + 1) for rank, hit in enumerate(relevant[:k], start=1) if hit)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(case.sources), k) + 1))
    return {
        f"recall@{k}": 1.0 if any(relevant[:k]) else 0.0,
        "mrr@10": 1 / first if first else 0.0,
        f"ndcg@{k}": gains / ideal if ideal else 0.0,
    }


# ---- promptfoo ----------------------------------------------------------------------------------------------------


def promptfoo_config(cases: Sequence[Case], answers: Path, *, provider: Path, assertions: Path) -> dict[str, Any]:
    return {
        "description": "Recorded answers, checked against the evaluation dataset",
        "prompts": ["{{question}}"],
        "providers": [{"id": f"file://{provider.resolve()}", "config": {"answers": str(answers.resolve())}}],
        "tests": [to_promptfoo(case, f"file://{assertions.resolve()}") for case in cases],
    }


def promptfoo_scores(
    cases: Sequence[Case],
    records: Sequence[Record],
    workdir: Path,
    *,
    provider: Path = Path("evals/promptfoo/recorded.py"),
    assertions: Path = Path("evals/promptfoo/assertions.js"),
) -> dict[str, dict[str, Any]]:
    """promptfoo's verdict on each case of its families: passed, and why not."""
    scored = [case for case in cases if case.family in PROMPTFOO_FAMILIES]
    if not scored:
        return {}
    workdir.mkdir(parents=True, exist_ok=True)
    answers = workdir / "answers.json"
    by_id = {record.id: record for record in records}
    answers.write_text(json.dumps({case.id: by_id[case.id].output for case in scored}, ensure_ascii=False))
    config = workdir / "promptfooconfig.json"
    config.write_text(json.dumps(promptfoo_config(scored, answers, provider=provider, assertions=assertions)))
    output = workdir / "promptfoo-results.json"
    command = ["npx", "-y", PROMPTFOO, "eval", "-c", str(config), "-o", str(output)]
    command += ["--no-cache", "--no-progress-bar", "--no-table", "--no-write", "-j", "8"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if not output.exists():
        raise RuntimeError(f"promptfoo wrote no results: {completed.stderr[-2000:]}")
    verdicts = {}
    for row in json.loads(output.read_text())["results"]["results"]:
        grading = row.get("gradingResult") or {}
        verdicts[row["vars"]["id"]] = {
            "passed": bool(row["success"]),
            "reason": grading.get("reason") or row.get("error"),
        }
    return verdicts


# ---- Ragas --------------------------------------------------------------------------------------------------------


def ragas_scores(
    cases: Sequence[Case], records: Sequence[Record], workdir: Path, *, project: Path = Path("evals/ragas")
) -> dict[str, dict[str, float | None]]:
    """Faithfulness and context recall of each regulation case, by Ragas in its own environment."""
    scored = [case for case in cases if case.family == "regulation"]
    if not scored:
        return {}
    by_id = {record.id: record for record in records}
    samples = workdir / "ragas-samples.jsonl"
    samples.parent.mkdir(parents=True, exist_ok=True)
    samples.write_text(
        "".join(
            json.dumps(
                {
                    "id": case.id,
                    "user_input": case.question,
                    "response": by_id[case.id].answer if by_id[case.id].answered else "",
                    "retrieved_contexts": by_id[case.id].contexts,
                    "reference": case.answer or "",
                },
                ensure_ascii=False,
            )
            + "\n"
            for case in scored
        )
    )
    output = workdir / "ragas-scores.json"
    command = ["uv", "run", "--project", str(project), "python", str(project / "score.py"), str(samples), str(output)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not output.exists():
        raise RuntimeError(f"Ragas failed: {completed.stderr[-2000:]}")
    scores: dict[str, dict[str, float | None]] = json.loads(output.read_text())
    return scores


# ---- report -------------------------------------------------------------------------------------------------------


@dataclass
class FamilyScore:
    family: str
    cases: int
    metrics: dict[str, float]
    errors: int = 0


def family_scores(
    cases: Sequence[Case],
    records: Sequence[Record],
    *,
    promptfoo: Mapping[str, Mapping[str, Any]],
    ragas: Mapping[str, Mapping[str, float | None]],
    judge: Mapping[str, Mapping[str, Any]],
) -> list[FamilyScore]:
    """One line per family, with the metric that fits it."""
    by_id = {record.id: record for record in records}
    lines = []
    for family in FAMILIES:
        members = [case for case in cases if case.family == family]
        if not members:
            continue
        metrics: dict[str, float] = {}
        verdicts = [promptfoo[case.id]["passed"] for case in members if case.id in promptfoo]
        if verdicts:
            name = {"out_of_corpus": "abstention", "safety": "safe"}.get(family, "accuracy")
            metrics[name] = _mean(verdicts)
        retrieval = [score for case in members if (score := retrieval_scores(case, by_id[case.id]))]
        for key in ("recall@5", "mrr@10", "ndcg@5"):
            if retrieval:
                metrics[key] = _mean([score[key] for score in retrieval])
        for key in ("faithfulness", "context_recall"):
            values = [value for case in members if (value := (ragas.get(case.id) or {}).get(key)) is not None]
            if values:
                metrics[key] = _mean(values)
        grades = [judge[case.id] for case in members if case.id in judge]
        if grades:
            metrics["grade/5"] = _mean([grade["score"] for grade in grades])
            metrics["graded_4+"] = _mean([grade["score"] >= 4 for grade in grades])
        if family not in ("out_of_corpus",):
            metrics["answered"] = _mean([by_id[case.id].answered for case in members])
        metrics["median_s"] = statistics.median(by_id[case.id].seconds for case in members)
        lines.append(FamilyScore(family, len(members), metrics, sum(bool(by_id[c.id].error) for c in members)))
    return lines


def table(lines: Sequence[FamilyScore]) -> str:
    rows = [f"{'family':<15}{'cases':>6}  metrics"]
    for line in lines:
        metrics = "  ".join(
            f"{name} {value:.2f}" if name != "median_s" else f"{name} {value:.1f}"
            for name, value in line.metrics.items()
        )
        errors = f"  errors {line.errors}" if line.errors else ""
        rows.append(f"{line.family:<15}{line.cases:>6}  {metrics}{errors}")
    return "\n".join(rows)


def check_thresholds(lines: Sequence[FamilyScore], thresholds: Mapping[str, Mapping[str, float]]) -> list[str]:
    """The metrics under their threshold, as messages; empty when every threshold holds."""
    failures = []
    by_family = {line.family: line for line in lines}
    for family, limits in thresholds.items():
        line = by_family.get(family)
        for metric, minimum in limits.items():
            value = line.metrics.get(metric) if line else None
            if value is not None and value < minimum:
                failures.append(f"{family} {metric} {value:.2f} < {minimum:.2f}")
    return failures


def push_run(
    run_name: str,
    dataset: str,
    records: Sequence[Record],
    case_scores: Mapping[str, Mapping[str, float | bool]],
    *,
    client: Any,
    metadata: Mapping[str, Any] | None = None,
) -> int:
    """Link each traced case to its Langfuse dataset item under `run_name`, and score its trace. Returns the
    number of cases linked."""
    linked = 0
    for record in records:
        if not record.trace_id:
            continue
        client.api.dataset_run_items.create(
            run_name=run_name,
            dataset_item_id=f"{dataset}:{record.id}",
            trace_id=record.trace_id,
            metadata=dict(metadata or {}),
        )
        for name, value in case_scores.get(record.id, {}).items():
            data_type = "BOOLEAN" if isinstance(value, bool) else "NUMERIC"
            client.create_score(trace_id=record.trace_id, name=f"eval.{name}", value=float(value), data_type=data_type)
        linked += 1
    client.flush()
    return linked


def case_scores(
    cases: Sequence[Case],
    records: Sequence[Record],
    *,
    promptfoo: Mapping[str, Mapping[str, Any]],
    ragas: Mapping[str, Mapping[str, float | None]],
    judge: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, float | bool]]:
    """Every score of every case, for Langfuse and the report."""
    by_id = {record.id: record for record in records}
    scores: dict[str, dict[str, float | bool]] = defaultdict(dict)
    for case in cases:
        if case.id in promptfoo:
            scores[case.id]["passed"] = bool(promptfoo[case.id]["passed"])
        if retrieval := retrieval_scores(case, by_id[case.id]):
            scores[case.id].update(retrieval)
        for key, value in (ragas.get(case.id) or {}).items():
            if value is not None:
                scores[case.id][key] = value
        if case.id in judge:
            scores[case.id]["grade"] = float(judge[case.id]["score"])
    return dict(scores)


def _mean(values: Sequence[float | bool]) -> float:
    return sum(float(value) for value in values) / len(values) if values else 0.0
