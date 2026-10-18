"""Debriefs prepared after each race (LAB-204): one per team, one on the moments that made the race, one per driver
on request; each run by the agent up to its review, then waiting in « En attente ».

The plan of a prepared debrief is approved by code: what the agent's plan node picked for a team or a driver, every
analysis for the moments (a plan fixed by code). Nothing is published without a person's review: a prepared debrief
shows on its race's page once reviewed point by point.

A debrief's thread id is derived from its race and target, so a batch run again skips what it already prepared and
goes on with what failed or was cut by the budget. The batch runs in this process, one debrief at a time: a debrief
is a graph of 10 to 20 model calls, not a single call the platform's job worker could run, and the f1 key's limit
of 100,000 tokens a minute sets the pace anyway.

    just debriefs-prepare 2025 --round 16                  # the teams and the moments of one race
    just debriefs-prepare 2025 --categories driver --round 16
    just debriefs-prepare 2025 --budget 2000000            # every race of 2025 in the lake, until the budget
"""

import argparse
import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol

from core.agent.graph import Run

log = logging.getLogger("f1.prepare")

Category = Literal["team", "moments", "driver"]
CATEGORIES: tuple[Category, ...] = ("team", "moments", "driver")
DEFAULT_CATEGORIES: tuple[Category, ...] = ("team", "moments")  # 11 a race; 20 more drivers' would make 31 reviews
# A batch stops starting debriefs once this many tokens are spent: a debrief costs 30,000 to 65,000 (LAB-207).
DEFAULT_BUDGET = 1_000_000
_NAMESPACE = uuid.UUID("5e1d0b6c-2f0e-4c1e-9d3a-204204204204")


@dataclass(frozen=True)
class Prepared:
    """One debrief to prepare: its category, its target (a team, a driver's code, nothing for the moments), the
    request the analyst would have written, and the subject fields chosen by code."""

    season: int
    round: int
    category: Category
    target: str
    request: str
    given: dict[str, Any]

    @property
    def thread_id(self) -> str:
        return str(uuid.uuid5(_NAMESPACE, f"{self.season}:{self.round}:{self.category}:{self.target}"))


def batch(
    season: int, round_number: int, entry: Sequence[Mapping[str, Any]], categories: Sequence[Category]
) -> list[Prepared]:
    """The debriefs of a race, the teams in their best car's finishing order (`entry` is in finishing order)."""
    race = {"season": season, "round": round_number}
    found: list[Prepared] = []
    if "moments" in categories:
        given = {**race, "prepared": "moments", "moments": True, "drivers": [], "teams": []}
        found.append(Prepared(season, round_number, "moments", "", "Les moments qui ont fait la course", given))
    if "team" in categories:
        for team in dict.fromkeys(str(driver["team"]) for driver in entry if driver.get("team")):
            codes = [str(driver["code"]) for driver in entry if driver.get("team") == team]
            given = {**race, "prepared": "team", "teams": [team], "drivers": codes}
            found.append(Prepared(season, round_number, "team", team, f"Débrief stratégique de {team}", given))
    if "driver" in categories:
        for driver in entry:
            code, name = str(driver["code"]), str(driver["name"])
            given = {**race, "prepared": "driver", "teams": [], "drivers": [code]}
            found.append(Prepared(season, round_number, "driver", code, f"Débrief stratégique de {name}", given))
    return found


class Agent(Protocol):
    def start(self, request: str, *, thread_id: str, given: Mapping[str, Any] | None = None) -> Run: ...
    def resume(self, thread_id: str, answer: Any) -> Run: ...
    def get(self, thread_id: str) -> Run: ...


Outcome = Literal["prepared", "skipped", "failed", "not_started"]


@dataclass
class Done:
    prepared: Prepared
    outcome: Outcome
    status: str = ""  # where the request stands: "waiting" for its review, "stopped", "published"...
    calls: int = 0
    tokens: int = 0
    seconds: float = 0.0
    error: str = ""


@dataclass
class Report:
    done: list[Done] = field(default_factory=list)

    def count(self, outcome: Outcome) -> int:
        return sum(item.outcome == outcome for item in self.done)

    @property
    def tokens(self) -> int:
        return sum(item.tokens for item in self.done)

    def markdown(self) -> str:
        rows = [
            f"| {item.prepared.season} {item.prepared.round} | {item.prepared.category} "
            f"| {item.prepared.target or '-'} "
            f"| {item.outcome} | {item.status or '-'} | {item.calls} | {item.tokens:,} | {item.seconds:.0f} s "
            f"| {item.error or ''} |"
            for item in self.done
        ]
        seconds = sum(item.seconds for item in self.done)
        return "\n".join([
            f"{self.count('prepared')} prepared, {self.count('skipped')} already there, {self.count('failed')} failed, "
            f"{self.count('not_started')} left for the budget; {self.tokens:,} tokens in {seconds / 60:.1f} min.",
            "",
            "| Race | Category | Target | Outcome | Status | Calls | Tokens | Time | Error |",
            "| -- | -- | -- | -- | -- | --: | --: | --: | -- |",
            *rows,
        ])  # fmt: skip


def prepare(agent: Agent, debriefs: Sequence[Prepared], *, budget: int = DEFAULT_BUDGET) -> Report:
    """Each debrief run to its review, one after the other; one already there is left as it is, one that failed
    before is started again, and none is started once the tokens spent reach the budget."""
    report = Report()
    for item in debriefs:
        if report.tokens >= budget:
            report.done.append(Done(item, "not_started"))
            continue
        try:
            existing = agent.get(item.thread_id)
        except KeyError:
            existing = None
        if existing is not None and existing.status != "stopped":
            report.done.append(Done(item, "skipped", status=existing.status))
            continue
        # Stopped before (a limit, an error): a new thread, the old one kept for the record.
        thread_id = (
            item.thread_id if existing is None else str(uuid.uuid5(_NAMESPACE, f"{item.thread_id}:{time.time_ns()}"))
        )
        report.done.append(_run(agent, item, thread_id))
        log.info("%s %s %s: %s", item.season, item.round, item.target or item.category, report.done[-1].outcome)
    return report


def _run(agent: Agent, item: Prepared, thread_id: str) -> Done:
    started = time.monotonic()
    try:
        run = agent.start(item.request, thread_id=thread_id, given=item.given)
        if run.waiting is not None and run.waiting.kind == "plan":
            picked = [a["id"] for a in run.waiting.payload["analyses"] if a.get("selected")]
            run = agent.resume(thread_id, picked)
    except Exception as error:  # one debrief failing never stops the batch
        return Done(item, "failed", seconds=time.monotonic() - started, error=f"{type(error).__name__}: {error}")
    spent = run.state.spent
    done = Done(item, "prepared", status=run.status, calls=spent.llm_calls, tokens=spent.tokens,
                seconds=time.monotonic() - started)  # fmt: skip
    if run.waiting is None or run.waiting.kind != "review":
        reason = run.waiting.kind if run.waiting else run.state.stop_reason or run.status
        return replace(done, outcome="failed", error=f"did not reach the review: {reason}")
    return done


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="f1-debriefs-prepare", description=__doc__.splitlines()[0] if __doc__ else None
    )
    parser.add_argument("season", type=int)
    parser.add_argument("--round", dest="rounds", type=int, action="append", help="only this round (repeatable)")
    parser.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES),
                        help=f"among {', '.join(CATEGORIES)} (default {','.join(DEFAULT_CATEGORIES)})")  # fmt: skip
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="tokens; no debrief starts beyond")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    categories = [name.strip() for name in args.categories.split(",")]
    if unknown := [name for name in categories if name not in CATEGORIES]:
        parser.error(f"unknown categories: {', '.join(unknown)}")

    from f1.agent import debrief_agent
    from f1.data import connect
    from f1.tools import RaceData

    data = RaceData(connect())
    rounds = args.rounds or [int(event["round"]) for event in data.events(args.season)]
    debriefs = []
    for round_number in rounds:
        entry = data.drivers(args.season, round_number)
        if not entry:
            log.warning("no race result for %s round %s: skipped", args.season, round_number)
            continue
        debriefs += batch(args.season, round_number, entry, categories)
    log.info("%d debriefs to prepare, budget %s tokens", len(debriefs), f"{args.budget:,}")
    with debrief_agent() as agent:
        report = prepare(agent, debriefs, budget=args.budget)
    print(report.markdown())
    return 1 if report.count("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
