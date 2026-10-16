"""`just eval-dataset`: build the F1 evaluation dataset, check it, push it to Langfuse.

just eval-dataset                    # build: computed cases + handwritten/ -> dev.jsonl and test.jsonl
just eval-dataset check              # rebuild in memory and compare with the files: the same lake, the same bytes
just eval-dataset push               # Langfuse datasets f1-dev and f1-test, in the f1 project
just eval-dataset draft-regulation   # draft the regulation cases with chat-pro (once; then review them)
just eval-dataset review-candidates  # the points rejected or corrected in review for a wrong number or source
"""

import argparse
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from core.evals.dataset import FAMILIES, Case, check_unique, push_to_langfuse, read_cases, split_cases, write_cases
from f1.data import connect
from f1.evals.generate import SEED, generate
from f1.evals.strategy import load_decisions

DATASETS = Path("evals/datasets")
HANDWRITTEN = DATASETS / "handwritten"
# A third of the cases for tuning and calibration; the rest only measures.
DEV_SHARE = 0.3


def build() -> list[Case]:
    handwritten = [case for path in sorted(HANDWRITTEN.glob("*.jsonl")) for case in read_cases(path)]
    computed = generate(connect(), decisions=load_decisions())
    cases = split_cases([*computed, *handwritten], seed=SEED, dev_share=DEV_SHARE)
    check_unique(cases)
    return cases


def write(cases: Sequence[Case], directory: Path) -> None:
    for split in ("dev", "test"):
        write_cases(directory / f"{split}.jsonl", [case for case in cases if case.split == split])


def table(cases: Sequence[Case]) -> str:
    counts = Counter((case.family, case.split) for case in cases)
    lines = [f"{'family':<15}{'dev':>6}{'test':>6}{'total':>7}"]
    for family in FAMILIES:
        dev, test = counts[(family, "dev")], counts[(family, "test")]
        lines.append(f"{family:<15}{dev:>6}{test:>6}{dev + test:>7}")
    dev, test = sum(case.split == "dev" for case in cases), sum(case.split == "test" for case in cases)
    lines.append(f"{'all':<15}{dev:>6}{test:>6}{dev + test:>7}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-eval-dataset", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "command",
        nargs="?",
        default="build",
        choices=["build", "check", "push", "draft-regulation", "review-candidates"],
    )
    args = parser.parse_args(argv)

    if args.command == "draft-regulation":
        from f1.evals.draft import OUTPUT, draft

        print(f"{len(draft())} regulation cases in {OUTPUT}: review them before building")
        return 0
    if args.command == "review-candidates":
        from core.agent.store import RequestStore
        from f1.evals.review import OUTPUT, export

        count = export(RequestStore().decisions(actions=["correct", "reject"], limit=10_000))
        print(f"{count} candidate cases in {OUTPUT}: complete each one, then move it to {HANDWRITTEN}")
        return 0
    if args.command == "push":
        for split in ("dev", "test"):
            cases = read_cases(DATASETS / f"{split}.jsonl")
            description = f"F1 strategy analyst, {split} set (LAB-146): {len(cases)} cases"
            print(f"f1-{split}: {push_to_langfuse(f'f1-{split}', cases, description=description)} items")
        return 0

    cases = build()
    if args.command == "check":
        with tempfile.TemporaryDirectory() as directory:
            write(cases, Path(directory))
            different = [
                split
                for split in ("dev", "test")
                if (Path(directory) / f"{split}.jsonl").read_bytes() != (DATASETS / f"{split}.jsonl").read_bytes()
            ]
        if different:
            print(f"rebuilt {', '.join(different)} differ from the files: rerun `just eval-dataset`")
            return 1
        print("the rebuilt dataset is the same, byte for byte")
        return 0
    write(cases, DATASETS)
    print(table(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
