"""`just debrief`: a strategy debrief by the agent, its three stops answered in the terminal.

    just debrief "Débrief stratégique du GP d'Italie 2025 pour Ferrari"
    just debrief --resume <thread>              # a request waiting, after a restart: it goes on where it stopped
    just debrief --resume <thread> --answer '["result", "stops:LEC"]'   # one answer as JSON, then stop

Needs the stack (`just up`: PostgreSQL keeps the requests), the corpus and the gateway. The front of LAB-152 will
answer the same stops; this is the way to run the graph without it.
"""

import argparse
import json
import logging
import sys
import uuid
from collections.abc import Sequence
from typing import Any

from core.agent import Agent, Run, Waiting

REASONS = {
    "1": "wrong_number",
    "2": "wrong_meaning",
    "3": "wrong_source",
    "4": "off_topic",
    "5": "wording",
    "6": "other",
}


def ask_clarification(waiting: Waiting) -> Any:
    print(f"\n? {waiting.payload['question']}")
    for number, option in enumerate(waiting.payload["options"], start=1):
        print(f"  {number}. {option['label']}")
    return int(input("Numéro : ").strip()) - 1


def ask_plan(waiting: Waiting) -> list[str]:
    analyses = waiting.payload["analyses"]
    selected = {analysis["id"] for analysis in analyses if analysis["selected"]}
    while True:
        print("\nPlan proposé (le numéro coche ou décoche, Entrée valide) :")
        for number, analysis in enumerate(analyses, start=1):
            print(f"  [{'x' if analysis['id'] in selected else ' '}] {number}. {analysis['label']}")
        typed = input("> ").strip()
        if not typed:
            return [analysis["id"] for analysis in analyses if analysis["id"] in selected]
        for token in typed.replace(",", " ").split():
            if token.isdigit() and 1 <= int(token) <= len(analyses):
                selected ^= {analyses[int(token) - 1]["id"]}


def ask_review(waiting: Waiting) -> list[dict[str, Any]]:
    decisions = []
    print("\nRevue point par point : a approuver, c corriger, r rejeter.")
    for point in waiting.payload["points"]:
        status = {"unverified": " [NON VÉRIFIÉ]", "unavailable": " [donnée indisponible]"}.get(point["status"], "")
        print(f"\n{point['id']}{status} : {point['text']}")
        for problem in point["problems"]:
            print(f"   ! {problem}")
        action = {"a": "approve", "c": "correct", "r": "reject"}.get(input("a/c/r > ").strip().lower()[:1], "approve")
        decision: dict[str, Any] = {"point": point["id"], "action": action}
        if action == "correct":
            decision["text"] = input("Texte corrigé : ").strip()
        if action != "approve":
            typed = input(
                "Motif (1 chiffre faux, 2 sens faux, 3 source fausse, 4 hors sujet, 5 formulation, 6 autre) : "
            ).strip()
            decision["reason"] = REASONS.get(typed, "other")
        decisions.append(decision)
    return decisions


ASK = {"clarification": ask_clarification, "plan": ask_plan, "review": ask_review}


def drive(agent: Agent, run: Run) -> int:
    while run.waiting is not None:
        print(f"(demande {run.thread_id} en attente : {run.waiting.kind})")
        run = agent.resume(run.thread_id, ASK[run.waiting.kind](run.waiting))
    return report(run)


def report(run: Run) -> int:
    spent = run.state.spent
    print(f"\n{run.status} · {spent.steps} étapes, {spent.llm_calls} appels de modèle, {spent.tokens} tokens")
    if run.state.status == "stopped":
        print(f"Arrêtée : {run.state.stop_reason}")
        return 1
    if run.state.deliverable:
        print("\n" + run.state.deliverable)
    elif run.waiting is not None:
        print(f"En attente ({run.waiting.kind}) : `just debrief --resume {run.thread_id}`")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-debrief", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("request", nargs="?", help="the request, in French")
    parser.add_argument("--resume", metavar="THREAD", help="go on with a waiting request")
    parser.add_argument("--answer", help="with --resume: one answer as JSON, then stop at the next stop")
    args = parser.parse_args(argv)
    if not (args.request or args.resume):
        parser.error("give a request, or --resume a waiting one")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    from f1.agent import debrief_agent

    with debrief_agent() as agent:
        if args.resume and args.answer is not None:
            return report(agent.resume(args.resume, json.loads(args.answer)))
        run = agent.get(args.resume) if args.resume else agent.start(args.request, thread_id=str(uuid.uuid4()))
        return drive(agent, run)


if __name__ == "__main__":
    sys.exit(main())
