"""Measure the retrieval pipeline on the development set, stage by stage, and calibrate the abstention threshold.

`just rag-eval` runs steps 1 to 4 (no answer is written) under each configuration of the ablation, each adding one
stage to the previous one, then picks the threshold on the top rerank score that best separates the questions to
answer from those to abstain on. The test set (LAB-146) is never used here.
"""

import argparse
import json
import logging
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from core.retrieval.evaluation import Outcome, calibrate, load_cases, metrics, run, with_threshold
from core.retrieval.pipeline import PipelineConfig, Retrieval, RetrievalPipeline
from f1.rag import rag_pipeline

DEV_SET = Path("evals/datasets/dev.jsonl")  # never the test set: the threshold is calibrated here
REPORTS = Path("evals/rag/reports")
# A question makes up to three gateway calls (rewrite, embeddings, rerank), and the f1 key allows 60 per minute.
# The gateway client would wait out the limit anyway, but the wait would count in the latency measured.
SECONDS_PER_QUESTION = 3.0
OFF: dict[str, Any] = {"abstain": False}  # the gate is applied afterwards, at each threshold
# Each configuration adds one stage to the one before.
ABLATION: dict[str, dict[str, Any]] = {
    "dense": {"rewrite": False, "references": False, "sparse": False, "rerank": False},
    "+ bm25 (hybrid, RRF)": {"rewrite": False, "references": False, "rerank": False},
    "+ rewrite (English query)": {"multi_query": False, "references": False, "rerank": False},
    "+ multi-query": {"references": False, "rerank": False},
    "+ references": {"rerank": False},
    "+ rerank": {},
}
# The whole pipeline without one stage: what that stage brings once the others are there.
LEAVE_ONE_OUT: dict[str, dict[str, Any]] = {
    "all but bm25": {"sparse": False},
    "all but rewrite": {"rewrite": False},
    "all but multi-query": {"multi_query": False},
}


def evaluate(pipeline: RetrievalPipeline, cases_path: Path) -> list[Outcome]:
    cases = load_cases(cases_path)

    def retrieve(question: str) -> tuple[Retrieval, float]:
        start = time.perf_counter()
        retrieval = pipeline.retrieve(question)
        elapsed = time.perf_counter() - start
        time.sleep(max(0.0, SECONDS_PER_QUESTION - elapsed))
        return retrieval, elapsed

    return run(cases, retrieve)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-rag-eval", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--cases", type=Path, default=DEV_SET)
    parser.add_argument("--only", help="run one configuration of the ablation, e.g. '+ rerank'")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="calibrate on this many runs of the whole pipeline and average: the rewrite varies from run to run",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

    base = PipelineConfig()
    every = ABLATION | LEAVE_ONE_OUT
    configurations = {args.only: every[args.only]} if args.only else every
    report: dict[str, Any] = {"date": date.today().isoformat(), "cases": str(args.cases), "configurations": {}}
    print(f"{'configuration':28s} {'R@1':>5s} {'R@5':>5s} {'MRR@10':>7s} {'median s':>9s}")
    full: list[Outcome] = []
    for name, switches in configurations.items():
        config = base.model_copy(update={**OFF, **switches})
        outcomes = evaluate(rag_pipeline(config), args.cases)
        scores = metrics(outcomes)
        report["configurations"][name] = {"switches": switches, "metrics": scores}
        print(
            f"{name:28s} {scores['recall@1']:5.2f} {scores['recall@5']:5.2f} {scores['mrr@10']:7.2f}"
            f" {scores['median_seconds']:9.2f}"
        )
        if not switches:  # the whole pipeline
            full = outcomes

    if full and args.runs > 1:
        whole = base.model_copy(update=OFF)
        thresholds = [calibrate(full).threshold]
        for _ in range(args.runs - 1):
            thresholds.append(calibrate(evaluate(rag_pipeline(whole), args.cases)).threshold)
        report["thresholds"] = thresholds
        print(
            f"\nThresholds over {args.runs} runs: {', '.join(f'{t:.3f}' for t in thresholds)};"
            f" mean {statistics.mean(thresholds):.3f}, spread {statistics.pstdev(thresholds):.3f}"
        )

    if full:
        calibration = calibrate(full)
        gated = metrics(with_threshold(full, calibration.threshold))
        report["calibration"] = asdict(calibration) | {"metrics": gated}
        report["cases_detail"] = [{"question": o.case.question, "rank": o.rank, "top_score": o.top_score} for o in full]
        print(
            f"\nThreshold {calibration.threshold:.3f}: right decision on {calibration.accuracy:.0%} of the questions,"
            f" answers {calibration.answered_in_corpus:.0%} of those whose source is in the top 5,"
            f" abstains on {calibration.abstained_out_of_corpus:.0%} of the others"
            f" ({gated.get('correct_abstention', 0):.0%} of the out-of-corpus questions)."
        )
        print("Set RAG_THRESHOLD in .env, or change PipelineConfig.threshold, to apply it.")
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{args.cases.stem}-{date.today().isoformat()}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
