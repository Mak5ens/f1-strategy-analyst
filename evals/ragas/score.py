"""Ragas scores of recorded answers: `uv run --project evals/ragas python evals/ragas/score.py <samples> <output>`.

Run by `just eval` (core.evals.harness.ragas_scores). Each sample is a regulation case answered by the system:
- faithfulness: the share of the answer's statements its contexts support (no answer: no score);
- context_recall: the share of the reference answer's statements the contexts hold.

The judge model is the gateway's `chat-pro` (GATEWAY_URL, GATEWAY_API_KEY, with the f1 key): the same model as the
systems it scores, a limit stated in docs/evaluation.md.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextRecall, Faithfulness

MODEL = os.environ.get("EVAL_JUDGE_MODEL", "chat-pro")
CONCURRENCY = 4


async def score(samples: list[dict], output: Path) -> None:
    client = AsyncOpenAI(
        base_url=os.environ.get("GATEWAY_URL", "http://localhost:4000"),
        api_key=os.environ["GATEWAY_API_KEY"],
        max_retries=6,  # a 429 of the team's limit is retried after its retry-after
    )
    llm = llm_factory(MODEL, client=client)
    faithfulness, recall = Faithfulness(llm=llm), ContextRecall(llm=llm)
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(sample: dict) -> tuple[str, dict]:
        async with gate:
            result: dict = {"faithfulness": None, "context_recall": None}
            contexts = sample["retrieved_contexts"] or [""]
            try:
                if sample["response"]:
                    found = await faithfulness.ascore(
                        user_input=sample["user_input"], response=sample["response"], retrieved_contexts=contexts
                    )
                    result["faithfulness"] = float(found.value)
                found = await recall.ascore(
                    user_input=sample["user_input"], retrieved_contexts=contexts, reference=sample["reference"]
                )
                result["context_recall"] = float(found.value)
            except Exception as error:
                result["error"] = f"{type(error).__name__}: {error}"[:500]
            return sample["id"], result

    scores = dict(await asyncio.gather(*(one(sample) for sample in samples)))
    output.write_text(json.dumps(scores, indent=1))


def main() -> int:
    samples_path, output = Path(sys.argv[1]), Path(sys.argv[2])
    samples = [json.loads(line) for line in samples_path.read_text().splitlines() if line.strip()]
    asyncio.run(score(samples, output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
