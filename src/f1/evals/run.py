"""`just eval`: the evaluation of a system on the dataset, one table of scores per family.

    just eval                          # the baseline on the test set
    just eval --sample 8               # at most 8 cases per family: a quick look, within the rate limit
    just eval --family strategy        # one family only (its thresholds are updated alone)
    just eval --split dev --push       # the development set, and the run in Langfuse
    just eval --check                  # fail when a family falls under the main branch's reference runs
    just eval --sample 10 --check --budget 0.25   # the CI's quick gate (.github/workflows/eval.yml)
    just eval --run-name <run> --resume   # go on with an interrupted run: only the missing or failed cases
    just eval judge-sheet              # 30 strategy answers graded by the judge, for a person to grade too
    just eval agreement                # how the judge agrees with the person's grades (latest round)
    just eval thresholds --from evals/reports/<run>.json   # initial thresholds from a reference run

The system runs once per case; promptfoo, Ragas and the judge then score what it recorded (`core.evals.harness`).
Work files go to `.cache/evals/<run>/`, the report to `evals/reports/<run>.json`, and its summary, for a pull
request comment, to `.cache/evals/<run>/summary.md`.
"""

import argparse
import json
import logging
import math
import random
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.baseline import Baseline
from core.evals.compare import MARGIN, NOISE_CASES, CaseScores, compare, markdown
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
from core.evals.judge import (
    SheetLabels,
    agreement,
    calibration_markdown,
    calibration_sheet,
    grade,
    read_markdown_grades,
)
from core.gateway import gateway_client, key_spend
from f1.evals.build import DATASETS

log = logging.getLogger("f1.eval")

WORK = Path(".cache/evals")
REPORTS = Path("evals/reports")
THRESHOLDS = Path("evals/thresholds.json")
# One directory a calibration round, by date: `calibration.jsonl` is what the person grades (no judge grade in sight),
# `judge-grades.json` the judge's grades, `agreement.json` how close they are.
JUDGE = Path("evals/judge")
SHEET_SIZE = 30
# A round is drawn by kind, so that the cases where the judge is most likely wrong are there: false premises (an order
# that held, a premise reversed), penalties, neutralizations, the rare causes; then overcuts and undercuts.
SHEET_QUOTAS: list[tuple[str, int]] = [
    ("cause:no_swap", 5),
    ("question:false_premise -cause:no_swap", 5),  # a swap asked the other way round
    ("cause:penalty", 5),
    ("cause:neutralization", 5),
    ("cause:slow_stop", 1),
    ("cause:weather", 1),
    ("cause:double_stack", 1),
    ("cause:overcut", 3),
    ("cause:undercut", 4),
]
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


def spend() -> float | None:
    """The key's spend so far, or None when the gateway cannot tell (an older gateway, a key without the right)."""
    try:
        return key_spend()
    except Exception as error:
        log.warning("spend of the key unknown: %s", error)
        return None


def settled_spend(*, pause: float = 15.0, tries: int = 6) -> float | None:
    """The spend once the gateway has written the last calls: the same twice in a row, `pause` seconds apart."""
    last = spend()
    for _ in range(tries):
        if last is None:
            return None
        time.sleep(pause)
        now = spend()
        if now == last:
            return now
        last = now
    return last


def references(families: Sequence[str]) -> dict[str, tuple[str, CaseScores]]:
    """Each family's reference run on the main branch (`from_runs` of evals/thresholds.json) and its case scores."""
    if not THRESHOLDS.exists():
        return {}
    runs: dict[str, str] = json.loads(THRESHOLDS.read_text()).get("from_runs", {})
    found = {}
    for family in families:
        path = REPORTS / f"{runs.get(family)}.json"
        if family in runs and path.exists():
            found[family] = (runs[family], json.loads(path.read_text())["cases"])
    return found


def evaluate(args: argparse.Namespace) -> int:
    started, spent_before = time.monotonic(), (None if args.records else spend())
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

        def over_budget() -> str | None:
            if args.budget is None or spent_before is None:
                return None
            now = spend()
            return f"budget of ${args.budget} spent" if now is not None and now - spent_before > args.budget else None

        fresh = {
            r.id: r
            for r in run_system(
                SYSTEMS[args.system](), todo, workers=args.workers, on_record=progress, stop=over_budget
            )
        }
        records = [kept.get(case.id) or fresh[case.id] for case in cases]
        write_records(records_path, records)

    promptfoo = promptfoo_scores(cases, records, workdir)
    ragas = {} if args.no_ragas else ragas_scores(cases, records, workdir)
    judge = {} if args.no_judge else judge_records(cases, records)
    lines = family_scores(cases, records, promptfoo=promptfoo, ragas=ragas, judge=judge)
    print(table(lines))

    scores = case_scores(cases, records, promptfoo=promptfoo, ragas=ragas, judge=judge)
    comparisons = compare(cases, scores, references([line.family for line in lines]), GATED)
    # A threshold holds for a whole family: a sample is only compared with the reference on the same cases.
    whole = not args.sample and not args.records
    under = check_thresholds(lines, json.loads(THRESHOLDS.read_text())["families"]) if whole else []
    spent_after = None if spent_before is None else settled_spend()
    cost = None if spent_after is None or spent_before is None else round(spent_after - spent_before, 4)
    minutes = round((time.monotonic() - started) / 60, 1)
    ids = {case.id for case in cases}
    errors = sum(bool(record.error) for record in records if record.id in ids)
    summary = markdown(
        comparisons,
        title=f"Evaluation: {args.system} on the {args.split} set"
        + (f", {args.sample} cases per family" if args.sample else ", every case"),
        other_failures=[f"{failure} (threshold of the whole family)" for failure in under],
        details=[
            f"{len(cases)} cases, {errors} in error · {minutes} min"
            + (f" · ${cost:.2f} spent by the gateway key" if cost is not None else ""),
            f"Run `{run}`: the reference runs are named in `evals/thresholds.json` (`from_runs`).",
        ],
        marker="<!-- f1-eval -->",
    )
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "summary.md").write_text(summary)
    report = {
        "run": run,
        "system": args.system,
        "split": args.split,
        "sample_per_family": args.sample,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "minutes": minutes,
        "cost_usd": cost,
        "comparison": [{**vars(c), "delta": c.delta, "regressed": c.regressed} for c in comparisons],
        "families": {line.family: {"cases": line.cases, "errors": line.errors, **line.metrics} for line in lines},
        "cases": scores,
        "judge": judge,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{run}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(summary)
    print(f"Report: {REPORTS / f'{run}.json'}  (records: {records_path}, summary: {workdir / 'summary.md'})")

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
        failures = [c for c in comparisons if c.regressed]
        for failure in under:
            print(f"under threshold: {failure}")
        return 1 if failures or under else 0
    return 0


LABELS = SheetLabels(
    title="Notation des réponses de stratégie",
    intro="Note chaque réponse de 1 à 5 sur la ligne « Note », sans regarder les notes du juge "
    "(`judge-grades.json`), puis lance `just eval agreement`.",
    question="Question",
    reference="Référence",
    answer="Réponse du système",
    grade="Note (1 à 5) :",
)
RUBRIC_FR = """\
| Note | Quand |
| -- | -- |
| 5 | La cause principale de la référence, avec les faits qui l'appuient, et rien de faux |
| 4 | La cause principale ; les faits sont partiels ou vagues, mais rien n'est faux |
| 3 | La cause est citée, mais pas comme la principale, ou un détail est faux |
| 2 | Une autre cause principale, même si certains faits sont justes |
| 1 | Faux, inventé, ou pas de réponse |

Quand la référence commence par « Prémisse fausse », la correction est la cause principale : une réponse qui accepte \
la prémisse vaut 1 ; une réponse qui la corrige se note sur le reste comme ci-dessus."""


def split_reference(text: str) -> list[str]:
    """A strategy reference as a list: the premise, the cause and each driver's stop, their details nested."""
    lines: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        premise, _, rest = line.partition(" Cause principale : ")
        if rest and premise:  # "Prémisse fausse : ..." or "X est sorti devant Y." before the cause
            lines.append(_bold_label(premise))
            line = f"Cause principale : {rest}"
        head, sep, details = line.partition(" : ")
        if head == "Cause principale":
            clauses = details.replace("sur le cycle d'arrêts : ", "sur le cycle d'arrêts ; ").split(" ; ")
            lines.append(f"**{head} :** {clauses[0]}")
            lines += [f"  - {clause}" for clause in clauses[1:]]
        elif sep and ", " in details and head != "Écarts" and len(head) < 40:  # a driver's stop
            lines.append(f"**{head} :**")
            lines += [f"  - {item}" for item in details.rstrip(".").split(", ")]
        else:
            lines.append(_bold_label(line))
    return lines


def _bold_label(line: str) -> str:
    head, sep, rest = line.partition(" : ")
    return f"**{head} :** {rest}" if sep and len(head) < 40 else line


def sheet_cases(cases: Sequence[Case], *, seed: int = SEED) -> list[Case]:
    """The strategy cases of a calibration round, drawn by SHEET_QUOTAS, each case at most once."""
    rng = random.Random(seed)
    chosen: list[Case] = []
    for kind, count in SHEET_QUOTAS:
        tag, _, without = kind.partition(" -")
        pool = [case for case in cases if tag in case.tags and without not in case.tags and case not in chosen]
        chosen += rng.sample(pool, min(count, len(pool)))
    rest = [case for case in cases if case not in chosen]
    return chosen + rng.sample(rest, max(0, min(SHEET_SIZE - len(chosen), len(rest))))


def judge_sheet(args: argparse.Namespace) -> int:
    """30 strategy cases answered by the system and graded by the judge, for a person to grade without looking at
    the judge's grade first. A new round goes to its own directory: an earlier round's grades are never lost."""
    directory = JUDGE / (args.round or f"{datetime.now(UTC):%Y-%m-%d}")
    if (directory / "calibration.jsonl").exists():
        print(f"{directory} already holds a round: give another --round")
        return 1
    cases = [case for case in read_cases(DATASETS / "dev.jsonl") + read_cases(DATASETS / "test.jsonl")]
    strategy = sheet_cases([case for case in cases if case.family == "strategy"])
    random.Random(SEED).shuffle(strategy)  # the kinds mixed, so that the order says nothing
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
    calibration_sheet(directory / "calibration.jsonl", rows)
    write_markdown(directory)
    (directory / "judge-grades.json").write_text(
        json.dumps(
            {case_id: {"judge": grade["score"], "reason": grade["reason"]} for case_id, grade in grades.items()},
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )
    print(f"{len(rows)} answers in {directory}/calibration.md: grade each one (1 to 5), then `just eval agreement`")
    return 0


def write_markdown(directory: Path) -> None:
    """The readable sheet of a round, from its `calibration.jsonl` (grades already there are kept)."""
    rows = [json.loads(line) for line in (directory / "calibration.jsonl").read_text().splitlines() if line.strip()]
    calibration_markdown(
        directory / "calibration.md", rows, labels=LABELS, rubric=RUBRIC_FR, split_reference=split_reference
    )


def judge_markdown(args: argparse.Namespace) -> int:
    """Write the readable sheet of a round made before it existed."""
    directory = JUDGE / args.round if args.round else sorted(p for p in JUDGE.iterdir() if p.is_dir())[-1]
    write_markdown(directory)
    print(f"{directory}/calibration.md")
    return 0


def judge_agreement(args: argparse.Namespace) -> int:
    """The person's grades are read from `calibration.md` when it exists, else from `human` in `calibration.jsonl`;
    they are then written back to `calibration.jsonl`, the round's data."""
    rounds = sorted(path for path in JUDGE.iterdir() if (path / "calibration.jsonl").exists())
    directory = JUDGE / args.round if args.round else rounds[-1]
    sheet = directory / "calibration.jsonl"
    rows = [json.loads(line) for line in sheet.read_text().splitlines() if line.strip()]
    if (directory / "calibration.md").exists():
        written = read_markdown_grades(directory / "calibration.md", labels=LABELS)
        rows = [{**row, "human": written.get(row["id"])} for row in rows]
        sheet.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    judge = json.loads((directory / "judge-grades.json").read_text())
    pairs = [(int(judge[row["id"]]["judge"]), int(row["human"])) for row in rows if row.get("human") is not None]
    result = agreement(pairs)
    (directory / "agreement.json").write_text(json.dumps(result, indent=1) + "\n")
    print(directory)
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
# Under the reference's score by more than MARGIN, or two cases of the family when that is more, a change made things
# worse (core.evals.compare): the same margin sets the thresholds below.


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
    parser.add_argument(
        "command", nargs="?", default="run", choices=["run", "judge-sheet", "judge-markdown", "agreement", "thresholds"]
    )
    parser.add_argument("--from", dest="from_report", help="thresholds: the reference run's report")
    parser.add_argument("--system", default="baseline", choices=sorted(SYSTEMS))
    parser.add_argument("--split", default="test", choices=["dev", "test"])
    parser.add_argument("--sample", type=int, help="at most this many cases per family")
    parser.add_argument("--family", action="append", choices=FAMILIES, help="only this family (repeatable)")
    parser.add_argument("--workers", type=int, default=4, help="cases run at once (the rate limit sets the pace)")
    parser.add_argument("--records", help="score this records.jsonl instead of running the system")
    parser.add_argument("--run-name")
    parser.add_argument("--round", help="judge-sheet, agreement: the calibration round (a date by default)")
    parser.add_argument("--resume", action="store_true", help="keep the cases a run of that name already answered")
    parser.add_argument("--no-ragas", action="store_true")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--push", action="store_true", help="link the run to the Langfuse dataset, with its scores")
    parser.add_argument(
        "--check", action="store_true", help=f"exit 1 when a family falls under its reference run or {THRESHOLDS}"
    )
    parser.add_argument("--budget", type=float, help="dollars the key may spend: the cases left are not run")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for noisy in ("httpx", "httpx2", "openai", "langfuse"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    commands = {
        "run": evaluate,
        "judge-sheet": judge_sheet,
        "judge-markdown": judge_markdown,
        "agreement": judge_agreement,
        "thresholds": thresholds,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
