"""The agent as the app answers a question (LAB-154), for `just eval --system agent`: the home page's free question
(LAB-206), routed by code, then answered on its path.

    rules -> the production retrieval pipeline (LAB-186): claims citing their passages, or an abstention
    data  -> the questions of LAB-205 on the race: analyses of a closed catalog, every number checked, or withheld

The app asks the analyst when it cannot decide; an evaluation has nobody to ask, so the system decides as an analyst
most often would, and records what it decided (`Record.meta`):

- no path (both kinds of words, or neither): data when the question names a race, a driver or a team, else rules;
- a debrief asked for: data, the same analyses answering the question directly;
- the race unclear (no season, two editions): no answer, as the app asks which race.
"""

import json
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from functools import cache
from typing import Any

from core.agent.chat import Reply
from core.evals.dataset import Case
from core.evals.harness import Record
from core.retrieval.pipeline import Answer
from f1.questions import PICK_RACE, FreeQuestions, RaceLink
from f1.router import Route, Router, Routing

MODEL = "chat-pro"  # every node of the agent and every answer of the pipeline (AGENT_*, RAG_* to change)


class AgentSystem:
    name = "agent"

    def __init__(self, questions: FreeQuestions | None = None, *, model: str | None = None) -> None:
        if model and model != MODEL:
            raise ValueError(f"the agent runs on {MODEL}; set AGENT_* and RAG_* to try another model")
        self.questions = questions or _questions()
        self.model = MODEL

    def run(self, case: Case) -> Record:
        routing = self.questions.router.route(case.question)
        path = path_for(routing)
        meta: dict[str, Any] = {"route": routing.route, "path": path, "reason": routing.reason}
        if path == "rules":
            return _rules(case, self.questions.rules(case.question), meta)
        race = self.questions.resolve(routing)
        if not isinstance(race, RaceLink):
            return Record(case.id, case.family, case.question, False, PICK_RACE, meta={**meta, "race": None})
        started = time.monotonic()
        reply = self.questions.data(case.question, race, routing)
        meta |= {"race": f"{race.season}/{race.round}", "seconds_data": round(time.monotonic() - started, 2)}
        if isinstance(reply, str):
            return Record(case.id, case.family, case.question, False, reply, meta=meta)
        return _data(case, reply, meta)


def path_for(routing: Routing) -> Route:
    """The path an evaluation takes: the router's, or the one an analyst would most often choose."""
    if routing.route == "debrief":
        return "data"
    if routing.route is None:
        return "data" if routing.named or routing.grands_prix else "rules"
    return routing.route


def _rules(case: Case, answer: Answer, meta: dict[str, Any]) -> Record:
    return Record(
        id=case.id,
        family=case.family,
        question=case.question,
        answered=answer.answered,
        answer="\n".join(claim.text for claim in answer.claims) if answer.answered else str(answer.abstention),
        contexts=[source.text for source in answer.sources] or [passage.text for passage in answer.retrieved[:5]],
        retrieved=[dict(passage.payload) for passage in answer.retrieved],
        trace_id=answer.trace_id,
        meta={**meta, "abstention": answer.abstention},
    )


def _data(case: Case, reply: Reply, meta: dict[str, Any]) -> Record:
    answered = reply.status == "answered"
    return Record(
        id=case.id,
        family=case.family,
        question=case.question,
        answered=answered,
        answer="\n".join(point.text for point in reply.points) if answered else reply.reason or reply.status,
        contexts=[json.dumps(result.output, ensure_ascii=False) for result in reply.results if result.ok]
        + [source.text for rule in reply.rules for source in rule.sources],
        retrieved=[],
        tool_calls=[
            {"tool": result.tool, "arguments": result.arguments, "error": result.error} for result in reply.results
        ],
        meta={**meta, "status": reply.status, "llm_calls": reply.spent.llm_calls, "tokens": reply.spent.tokens},
    )


def _questions() -> FreeQuestions:
    from f1.agent import debrief_chat
    from f1.data import connect
    from f1.grand_prix import GrandPrix
    from f1.rag import rag_pipeline

    grand_prix = GrandPrix(connect())
    return FreeQuestions(Router(*grand_prix.people()), grand_prix, rules=cache(rag_pipeline), chat=cache(debrief_chat))


# Why a case failed, from what the system recorded: the order is the one of the checks.
CAUSES = {
    "race": "race not identified",
    "number": "withheld: a number no analysis gives",
    "meaning": "withheld: a meaning the analyses do not show",
    "abstained": "abstained or refused",
    "wrong": "answered, wrong or incomplete",
}


def failed(score: Mapping[str, Any]) -> bool:
    """A case scored as a failure: an assertion not passed, a grade under 4, recall@5 under 1."""
    if "passed" in score:
        return not score["passed"]
    if "grade" in score:
        return float(score["grade"]) < 4
    if "recall@5" in score:
        return float(score["recall@5"]) < 1
    return False


def cause(record: Record) -> str:
    if record.meta.get("path") == "data" and record.meta.get("race") is None and not record.answered:
        return "race"
    if not record.answered and "numbers that are in none" in record.answer:
        return "number"
    if not record.answered and "sens," in record.answer:
        return "meaning"
    return "abstained" if not record.answered else "wrong"


def failure_causes(records: Sequence[Record], scores: Mapping[str, Mapping[str, Any]]) -> str:
    """The failed cases of a run by family and cause (LAB-154), as a Markdown table."""
    counts: dict[str, Counter[str]] = {}
    for record in records:
        if record.id in scores and failed(scores[record.id]) and record.family not in {"out_of_corpus", "safety"}:
            counts.setdefault(record.family, Counter())[cause(record)] += 1
    lines = ["| Family | " + " | ".join(CAUSES.values()) + " |", "| -- |" + " --: |" * len(CAUSES)]
    for family, found in counts.items():
        lines.append(f"| {family} | " + " | ".join(str(found[key]) for key in CAUSES) + " |")
    return "\n".join(lines)
