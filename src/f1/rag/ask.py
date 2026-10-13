"""Ask a question on the FIA rules from the terminal: `just ask "Peut-on changer de pneus sous drapeau rouge ?"`."""

import argparse
import logging
import sys
from collections.abc import Sequence

from core.retrieval.pipeline import AbstentionReason, Answer
from f1.rag import rag_pipeline

ABSTENTIONS: dict[AbstentionReason, str] = {
    "nothing_found": "Aucun passage du règlement ni des décisions ne correspond à cette question.",
    "below_threshold": "Je n'ai pas trouvé la réponse dans le règlement ni dans les décisions des commissaires.",
    "not_in_sources": "Les passages trouvés ne répondent pas à cette question.",
    "verification_failed": "Je n'ai pas pu écrire une réponse dont chaque point est appuyé par les sources.",
}


def render(answer: Answer) -> str:
    lines = [f"  ({note})" for note in answer.scope.notes]
    if answer.abstention:
        return "\n".join([ABSTENTIONS[answer.abstention], *lines])
    for claim in answer.claims:
        lines.append(f"- {claim.text} [{', '.join(claim.sources)}]")
    lines.append("")
    for source in answer.sources:
        url = source.passages[0].payload.get("url", "")
        lines.append(f"[{source.id}] {source.label}  {url}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1-ask", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("question")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    answer = rag_pipeline().answer(args.question)
    print(render(answer))
    if answer.trace_id:
        print(f"\nTrace Langfuse : {answer.trace_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
