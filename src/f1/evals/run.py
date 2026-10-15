"""`just eval`: the evaluation of a system on the dataset, one table of scores per family.

    just eval                          # the baseline on the test set
    just eval --sample 8               # at most 8 cases per family: a quick look, within the rate limit
    just eval --family strategy        # one family only (its thresholds are updated alone)
    just eval --split dev --push       # the development set, and the run in Langfuse
    just eval --check                  # fail when a family falls under its threshold (evals/thresholds.json)
    just eval --run-name <run> --resume   # go on with an interrupted run: only the missing or failed cases
    just eval judge-sheet              # 30 strategy answers graded by the judge, for a person to grade too
    just eval agreement                # how the judge agrees with the person's grades
    just eval thresholds --from evals/reports/<run>.json   # initial thresholds from a reference run

The system runs once per case; promptfoo, Ragas and the judge then score what it recorded (`core.evals.harness`).
Work files go to `.cache/evals/<run>/`, the report to `evals/reports/<run>.json`.
"""

import argparse
import json
import logging
import math
import random
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.baseline import Baseline
from core.evals.dataset import FAMILIES, Case, read_cases
from core.evals.harness import (
    Record,
    append_record,
    case_scores,
    check_thresholds,
    family_scores,
    promptfoo_scores,
    ragas_scores,
    read_records,
    run_system,
    sample,
    table,
    write_records,
)
from core.evals.judge import agreement, calibration_sheet, grade
from core.gateway import gateway_client
from f1.evals.build import DATASETS

log = logging.getLogger("f1.eval")

WORK = Path(".cache/evals")
REPORTS = Path("evals/reports")
THRESHOLDS = Path("evals/thresholds.json")
CALIBRATION = Path("evals/judge/calibration.jsonl")  # what the person grades: no judge grade in sight
JUDGE_GRADES = Path("evals/judge/judge-grades.json")
SEED = 148
END_USER = "f1-evals"  # the judge's calls, apart from the system's


class BaselineSystem:
    name = "baseline"

    def __init__(self, system: Baseline | None = None) -> None:
        from f1.baseline import baseline

        self.system = system or baseline()

    def run(self, case: Case) -> Record:
        result = self.system.answer(case.question)
        return Record(
            id=case.id,
            family=case.family,
            question=case.question,
            answered=result.answered,
            answer=result.answer,
            contexts=[source.text for source in result.retrieved]
            + [json.dumps(call.output, ensure_ascii=False) for call in result.tool_calls if call.output is not None],
            retrieved=[dict(source.payload) for source in result.retrieved],
            tool_calls=[
                {"tool": call.tool, "arguments": call.arguments, "error": call.error} for call in result.tool_calls
            ],
            trace_id=result.trace_id,
        )


SYSTEMS = {"baseline": BaselineSystem}


def judge_records(cases: Sequence[Case], records: Sequence[Record]) -> dict[str, dict[str, Any]]:
    client = gateway_client(end_user=END_USER)
    by_id = {record.id: record for record in records}
    grades = {}
    for case in cases:
        if case.family != "strategy":
            continue
        record = by_id[case.id]
        answer = record.answer if record.answered else "(no answer)"
        try:
            result = grade(client, question=case.question, reference=case.answer or "", answer=answer)
        except Exception as error:
            log.warning("judge failed on %s: %s", case.id, error)
            continue
        grades[case.id] = result.model_dump()
    return grades


def evaluate(args: argparse.Namespace) -> int:
    cases = [case for case in read_cases(DATASETS / f"{args.split}.jsonl") if case.family in (args.family or FAMILIES)]
    cases = sample(cases, args.sample, seed=SEED)
    run = args.run_name or f"{datetime.now(UTC):%Y%m%dT%H%M}-{args.system}-{args.split}" + (
        f"-{'-'.join(args.family)}" if args.family else ""
    ) + (f"-sample{args.sample}" if args.sample else "")
    workdir = WORK / run
    records_path = workdir / "records.jsonl"
    if args.records:  # score a run recorded earlier, without paying the system's calls again
        records = read_records(Path(args.records))
        cases = [case for case in cases if case.id in {record.id for record in records}]
    else:
        # Every record is appended as soon as its case is done. With --resume, the cases already answered without
        # an error are kept, and only the others run: an interrupted run (a restart, a gateway down) goes on.
        kept = (
            {r.id: r for r in read_records(records_path) if not r.error}
            if args.resume and records_path.exists()
            else {}
        )
        todo = [case for case in cases if case.id not in kept]
        log.info("%s on %d cases of the %s set (%d kept from before)", args.system, len(todo), args.split, len(kept))
        if records_path.exists():
            write_records(records_path, kept.values())
        done: list[Record] = []

        def progress(record: Record) -> None:
            done.append(record)
            append_record(records_path, record)
            log.info("[%d/%d] %s %s", len(done), len(todo), record.id, "ok" if not record.error else record.error)

        fresh = {r.id: r for r in run_system(SYSTEMS[args.system](), todo, workers=args.workers, on_record=progress)}
        records = [kept.get(case.id) or fresh[case.id] for case in cases]
        write_records(records_path, records)

    promptfoo = promptfoo_scores(cases, records, workdir)
    ragas = {} if args.no_ragas else ragas_scores(cases, records, workdir)
    judge = {} if args.no_judge else judge_records(cases, records)
    lines = family_scores(cases, records, promptfoo=promptfoo, ragas=ragas, judge=judge)
    print(table(lines))

    scores = case_scores(cases, records, promptfoo=promptfoo, ragas=ragas, judge=judge)
    report = {
        "run": run,
        "system": args.system,
        "split": args.split,
        "sample_per_family": args.sample,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "families": {line.family: {"cases": line.cases, "errors": line.errors, **line.metrics} for line in lines},
        "cases": scores,
        "judge": judge,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{run}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(f"Report: {REPORTS / f'{run}.json'}  (records: {records_path})")

    if args.push:
        from langfuse import Langfuse

        from core.evals.harness import push_run
        from core.tracing import LangfuseSettings

        settings = LangfuseSettings()
        assert settings.public_key and settings.secret_key, "LANGFUSE_* keys are needed to push a run"
        client = Langfuse(
            public_key=settings.public_key, secret_key=settings.secret_key.get_secret_value(), base_url=settings.host
        )
        linked = push_run(run, f"f1-{args.split}", records, scores, client=client, metadata={"system": args.system})
        print(f"Langfuse: {linked} cases linked to the dataset run {run}")

    if args.check:
        thresholds = json.loads(THRESHOLDS.read_text())
        failures = check_thresholds(lines, thresholds["families"])
        for failure in failures:
            print(f"under threshold: {failure}")
        return 1 if failures else 0
    return 0


def judge_sheet(args: argparse.Namespace) -> int:
    """30 strategy cases answered by the system and graded by the judge, for a person to grade without looking at
    the judge's grade first."""
    cases = [case for case in read_cases(DATASETS / "dev.jsonl") + read_cases(DATASETS / "test.jsonl")]
    strategy = random.Random(SEED).sample([case for case in cases if case.family == "strategy"], 30)
    records = run_system(SYSTEMS[args.system](), strategy, workers=args.workers)
    grades = judge_records(strategy, records)
    rows = [
        {
            "id": case.id,
            "question": case.question,
            "reference": case.answer,
            "answer": record.answer if record.answered else "(pas de réponse)",
        }
        for case, record in zip(strategy, records, strict=True)
    ]
    calibration_sheet(CALIBRATION, rows)
    JUDGE_GRADES.write_text(
        json.dumps(
            {case_id: {"judge": grade["score"], "reason": grade["reason"]} for case_id, grade in grades.items()},
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )
    print(f"{len(rows)} answers in {CALIBRATION}: set `human` (1 to 5) on each line, then `just eval agreement`")
    return 0


def judge_agreement(args: argparse.Namespace) -> int:
    rows = [json.loads(line) for line in CALIBRATION.read_text().splitlines() if line.strip()]
    judge = json.loads(JUDGE_GRADES.read_text())
    pairs = [(int(judge[row["id"]]["judge"]), int(row["human"])) for row in rows if row.get("human") is not None]
    result = agreement(pairs)
    (CALIBRATION.parent / "agreement.json").write_text(json.dumps(result, indent=1) + "\n")
    for key, value in result.items():
        print(f"{key:15s} {value:.2f}")
    return 0


# The metric a threshold holds for each family: the one that says whether the family works.
GATED = {
    "data": ["accuracy"],
    "computation": ["accuracy"],
    "strategy": ["grade/5"],
    "regulation": ["recall@5", "faithfulness"],
    "retrieval": ["recall@5"],
    "out_of_corpus": ["abstention"],
    "safety": ["safe"],
}
# Under the reference's score by more than this, a change made things worse: 0.05, or two cases of the family when
# that is more, so that one case answered differently by the model (noise, at temperature 0 too) fails no one.
MARGIN = 0.05
NOISE_CASES = 2


def thresholds(args: argparse.Namespace) -> int:
    """Thresholds from a reference run: its score on each gated metric, less the margin, rounded down. A family the
    run did not score keeps its threshold, and the run it came from."""
    report = json.loads(Path(args.from_report).read_text())
    current = json.loads(THRESHOLDS.read_text()) if THRESHOLDS.exists() else {}
    sources: dict[str, str] = current.get("from_runs") or {family: current["from"] for family in current["families"]}
    margins: dict[str, float] = dict(current.get("margins", {}))
    limits: dict[str, dict[str, float]] = dict(current.get("families", {}))
    for family, metrics in GATED.items():
        scores = report["families"].get(family, {})
        if not scores:
            continue
        margin = max(MARGIN, NOISE_CASES / scores["cases"])
        margins[family] = round(margin, 3)
        sources[family] = report["run"]
        limits[family] = {}
        for metric in metrics:
            if metric in scores:
                scale = 5.0 if metric == "grade/5" else 1.0
                value = max(0.0, scores[metric] - margin * scale)
                limits.setdefault(family, {})[metric] = math.floor(value * 100) / 100
    THRESHOLDS.write_text(json.dumps({"from_runs": sources, "margins": margins, "families": limits}, indent=1) + "\n")
    print(json.dumps(limits, indent=1))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-eval", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("command", nargs="?", default="run", choices=["run", "judge-sheet", "agreement", "thresholds"])
    parser.add_argument("--from", dest="from_report", help="thresholds: the reference run's report")
    parser.add_argument("--system", default="baseline", choices=sorted(SYSTEMS))
    parser.add_argument("--split", default="test", choices=["dev", "test"])
    parser.add_argument("--sample", type=int, help="at most this many cases per family")
    parser.add_argument("--family", action="append", choices=FAMILIES, help="only this family (repeatable)")
    parser.add_argument("--workers", type=int, default=4, help="cases run at once (the rate limit sets the pace)")
    parser.add_argument("--records", help="score this records.jsonl instead of running the system")
    parser.add_argument("--run-name")
    parser.add_argument("--resume", action="store_true", help="keep the cases a run of that name already answered")
    parser.add_argument("--no-ragas", action="store_true")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--push", action="store_true", help="link the run to the Langfuse dataset, with its scores")
    parser.add_argument("--check", action="store_true", help=f"exit 1 when a family is under {THRESHOLDS}")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for noisy in ("httpx", "httpx2", "openai", "langfuse"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    commands = {"run": evaluate, "judge-sheet": judge_sheet, "agreement": judge_agreement, "thresholds": thresholds}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
