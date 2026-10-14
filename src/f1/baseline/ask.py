"""`just baseline "<question>"`: the reference system's answer, its sources, the tools it called and its trace."""

import sys
from collections.abc import Sequence

from core.baseline import Result
from f1.baseline import baseline

WITHHELD = {
    "unverified_numbers": "Réponse retenue : elle donnait un chiffre qu'aucun outil ni aucune source ne contient.",
    "invalid_sources": "Réponse retenue : elle citait une source qui ne lui avait pas été donnée.",
}


def render(result: Result) -> str:
    lines = []
    if result.withheld:
        lines.append(WITHHELD[result.withheld])
        lines += [f"  - {problem}" for problem in result.problems]
    else:
        lines.append(result.answer if result.answered else f"(pas trouvé) {result.answer}")
    for call in result.tool_calls:
        lines.append(f"[outil] {call.tool}({call.arguments}){' -> ' + call.error if call.error else ''}")
    lines += [f"[{source.id}] {source.label}  {source.payload.get('url', '')}" for source in result.sources]
    if result.trace_id:
        lines.append(f"Trace Langfuse : {result.trace_id}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    question = " ".join(argv if argv is not None else sys.argv[1:]).strip()
    if not question:
        print('usage: f1-baseline "<question>"', file=sys.stderr)
        return 2
    print(render(baseline().answer(question)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
