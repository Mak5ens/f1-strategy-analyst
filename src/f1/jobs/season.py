"""`just season-jobs 2025`: one summary job per session of the season, through the platform's job queue.

Each session of the lake (practice, qualifying, sprint, race) becomes a job; the workers call the gateway with the
f1 key, whose rate limit sets the pace. Summaries are stored in the lake as they come back, under
`session_summaries/<season>/<round>-<session>.json`, with the facts they were written from, and the numbers and names
the check did not find in them. The batch's account (done, dead-lettered and why, missing) goes to
`session_summaries/<season>/_batches/<batch>.json`.
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from typing import Any

from core.jobs import Job, Report, Result, run_batch
from core.lake import Lake
from f1.data import connect
from f1.jobs import ALIAS, REPLY_QUEUE, simulated_job, summary_job, unverified_names, unverified_numbers
from f1.jobs.facts import session_facts

log = logging.getLogger("f1.season_jobs")


def summary_key(season: int, round_number: int, code: str) -> str:
    return f"session_summaries/{season}/{round_number:02d}-{code}.json"


def sessions(lake: Lake, season: int, rounds: Sequence[int] | None = None) -> list[tuple[int, str]]:
    """The (round, session) of the season in the lake, in the order they ran."""
    rows = (
        connect(lake)
        .execute("SELECT round, session FROM sessions WHERE season = ? ORDER BY start_utc", [season])
        .fetchall()
    )
    return [(int(round_number), str(code)) for round_number, code in rows if not rounds or round_number in rounds]


def build_jobs(
    lake: Lake,
    season: int,
    rounds: Sequence[int] | None = None,
    *,
    alias: str = ALIAS,
    simulate: tuple[float, float] | None = None,
) -> tuple[list[Job], dict[str, dict[str, Any]]]:
    """The jobs, and the facts each real one was written from (by job id)."""
    db = connect(lake)
    jobs, facts = [], {}
    for round_number, code in sessions(lake, season, rounds):
        if simulate:
            jobs.append(simulated_job(season, round_number, code, seconds=simulate[0], error_rate=simulate[1]))
            continue
        session = session_facts(db, season, round_number, code)
        job = summary_job(season, round_number, code, session, alias=alias)
        jobs.append(job)
        facts[job.id] = session
    return jobs, facts


def store(lake: Lake, season: int, result: Result, facts: dict[str, Any]) -> list[str]:
    """Store a summary with its facts; return the numbers and names of it the facts do not hold."""
    round_number, code = round_and_session(result.id)
    summary = str(result.reply.get("content") or "")
    numbers, names = unverified_numbers(summary, facts), unverified_names(summary, facts)
    lake.write_json(
        summary_key(season, round_number, code),
        {
            "id": result.id,
            "season": season,
            "round": round_number,
            "session": code,
            "event": facts.get("event"),
            "summary": summary,
            "unverified_numbers": numbers,
            "unverified_names": names,
            "alias": result.reply.get("alias"),
            "usage": result.reply.get("usage"),
            "seconds": result.reply.get("seconds"),
            "facts": facts,
        },
    )
    return numbers + names


def round_and_session(job: str) -> tuple[int, str]:
    """2025-r16-FP1 -> (16, "FP1")."""
    _, round_part, code = job.split("-", 2)
    return int(round_part.removeprefix("r")), code


def account(report: Report, unverified: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "batch": report.batch,
        "trace_id": report.trace_id,
        "seconds": round(report.seconds, 1),
        "tokens": report.tokens,
        "counts": {status: report.count(status) for status in ("done", "dead", "refused", "missing")},
        "jobs": {
            result.id: {
                "status": result.status,
                "reason": result.reason or None,
                "unverified": unverified.get(result.id),
            }
            for result in report.results.values()
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-season-jobs", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("season", type=int)
    parser.add_argument("--round", dest="rounds", type=int, action="append", help="only this round (repeatable)")
    parser.add_argument("--alias", default=ALIAS, help=f"gateway alias of the summaries (default {ALIAS})")
    parser.add_argument("--simulate", action="store_true", help="simulated jobs of the same volume: no model call")
    parser.add_argument("--simulate-seconds", type=float, default=2.0)
    parser.add_argument("--simulate-error-rate", type=float, default=0.05)
    parser.add_argument(
        "--idle-timeout", type=float, default=300.0, help="give up after this long with nothing back (seconds)"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("aiormq").setLevel(logging.WARNING)
    logging.getLogger("aio_pika").setLevel(logging.WARNING)

    lake = Lake()
    simulate = (args.simulate_seconds, args.simulate_error_rate) if args.simulate else None
    jobs, facts = build_jobs(lake, args.season, args.rounds, alias=args.alias, simulate=simulate)
    if not jobs:
        log.error("no session of %s in the lake: run `just ingest %s` first", args.season, args.season)
        return 1
    log.info("%d sessions of %s to summarize%s", len(jobs), args.season, " (simulated)" if simulate else "")

    unverified: dict[str, list[str]] = {}

    def on_result(result: Result) -> None:
        if result.status == "done" and not simulate:
            unverified[result.id] = store(lake, args.season, result, facts[result.id])
        log.info("%s %s %s", result.id, result.status, result.reason)

    report = asyncio.run(run_batch(jobs, reply_queue=REPLY_QUEUE, idle_timeout=args.idle_timeout, on_result=on_result))
    lake.write_json(f"session_summaries/{args.season}/_batches/{report.batch}.json", account(report, unverified))
    log.info("%s", report.summary())
    if not simulate:
        flagged = sum(bool(numbers) for numbers in unverified.values())
        log.info("%d of %d summaries have a number or a name the facts do not hold", flagged, len(unverified))
    return 0 if report.count("missing") == report.count("refused") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
