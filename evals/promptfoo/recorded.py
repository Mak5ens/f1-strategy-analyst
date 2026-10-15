"""promptfoo provider of recorded answers: the system under test ran once (`just eval`), promptfoo only checks.

The answers file maps a case id to the answer the system gave; the test's `id` variable names the case.
"""

import json
from functools import cache
from typing import Any


@cache
def _answers(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as file:
        answers: dict[str, str] = json.load(file)
    return answers


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    case_id = context["vars"]["id"]
    answers = _answers(options["config"]["answers"])
    if case_id not in answers:
        return {"error": f"no recorded answer for {case_id}"}
    return {"output": answers[case_id]}
