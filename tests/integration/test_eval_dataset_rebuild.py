"""The evaluation dataset against the lake: rebuilding it gives the committed files, byte for byte."""

import tempfile
from pathlib import Path

import pytest

from core.evals.dataset import FAMILIES, read_cases
from f1.evals.build import DATASETS, build, write

pytestmark = pytest.mark.integration


def test_rebuilding_the_computed_cases_gives_exactly_the_same_set() -> None:
    cases = build()
    with tempfile.TemporaryDirectory() as directory:
        write(cases, Path(directory))
        for split in ("dev", "test"):
            assert (Path(directory) / f"{split}.jsonl").read_bytes() == (DATASETS / f"{split}.jsonl").read_bytes(), (
                split
            )


def test_every_case_has_a_family_an_expectation_and_an_origin() -> None:
    cases = read_cases(DATASETS / "dev.jsonl") + read_cases(DATASETS / "test.jsonl")
    assert 300 <= len(cases) <= 500
    assert {case.family for case in cases} == set(FAMILIES)
    for case in cases:
        expected = case.answer or case.value is not None or case.sources or case.abstain or case.must_not_contain
        assert expected, case.id
        assert case.origin.by, case.id
