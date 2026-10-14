# ADR-024: A retrieval pipeline in six steps, each measured, with abstention

- **Status:** Accepted
- **Date:** 2026-10-12

## Context

The app answers questions on the FIA rules for a strategy analyst, in French, from an English corpus: the sporting regulations of 2024 to 2026 and 825 stewards' decisions, 2,872 chunks indexed by LAB-145 (`docs/corpus.md`).
A wrong rule stated with confidence is worse than no answer: an analyst would build a strategy call on it. So the pipeline must cite every claim, and say "not found" rather than guess.
The plan of 2026-10-10 asked for a production pipeline, every stage justified by a measure, as opposed to the "embeddings, top 5, answer" baseline that LAB-147 keeps as a reference.

Facts measured while building it, on the development set of 36 French questions (then `evals/rag/dev.jsonl`, now in the development set of `evals/datasets/`: 30 with expected sources, 6 outside the corpus):

- The gateway's small models cannot do the job: asked to rewrite a question as JSON, `qwen2.5:0.5b` repeated an array item until the timeout, and `qwen2.5:1.5b` copied the example of its prompt ("Italian Grand Prix") into the filters of a question about no race. LAB-185 added `chat-medium` (qwen2.5:7b, local GPU) and `chat-pro` (Mistral Small 3.2, Scaleway).
- `chat-medium` rewrites well, but answered "not found" on two of three questions whose sources held the answer; `chat-pro` answered them, each claim cited.
- A rewrite can bend the question: `chat-medium` turned "Quelle est la règle du hors-jeu au football ?" into "What is the pit lane rule in Formula 1?", and the reranker then scored a pit lane article 0.98.

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. A fixed pipeline of six steps (understand, search, rerank, gate, generate, verify), each a function with a switch, a span and a metric | Each stage's gain is measured, each failure has a place in the trace; abstention at three levels | More code and more model calls than a plain RAG: about 6 s and a tenth of a cent per question |
| B. A framework's query engine (LlamaIndex, LangChain retrievers) | Less code to write | Stages are hidden behind defaults: switching one off for an ablation, or tracing why a passage was kept, means fighting the framework; LlamaIndex was already set aside for the corpus (`docs/corpus.md`) |
| C. An agent that decides when and how to search (agentic RAG) | Handles multi-hop questions | Unbounded calls and latency, behaviour hard to test; the controlled agent of LAB-151 calls this pipeline as one of its tools instead |

## Decision

We choose **A**, in `core.retrieval.pipeline` (generic) with a theme profile in `f1.rag.profile`, and these choices inside it:

1. **Filters come from code, never from the model.** The season (a year, "la saison dernière"), the Grand Prix (from French names of countries, cities and circuits) and the explicit references ("article 55.14", "B5.13") are read by regular expressions. A wrong filter hides the answer for sure; a missed one only widens the search. Without a season, the latest one applies and the answer says so.
2. **The model rewrites, for recall only.** It writes the question as a standalone English query in the words of the regulations, plus two variants (multi-query); the prompt names the regulations' words for common terms ("suspended" for a red flag: without it, the article on red flags was not even among the 50 candidates).
3. **Hybrid search with RRF**: dense vectors (meaning) and BM25 (exact terms, article numbers) for each variant, fused by reciprocal rank in one Qdrant query, 50 candidates, under the season filter. Explicit references are looked up by metadata and pinned first.
4. **The reranker reads the rewrite**, in English. Against the French question, it found the same sources, but gave right answers scores as low as off-topic questions (down to 0.07 against 0.066): no threshold could separate them. Against the rewrite, sources found score 0.20 and more, off-topic questions 0.04 and less. The price is a dependency on the rewrite keeping the subject, which its prompt now demands (see Context: the football question).
5. **The gate abstains under a rerank score of 0.14**, calibrated on the development set (halfway between the scores that best separate the questions to answer from the others, the higher one on a tie), never on the test set. A question that names an article always passes. Passages under the threshold are not sent to the model either: they were stewards' decisions on unrelated matters, noise that costs tokens.
6. **The model answers from parents** (the whole article or decision, up to 6,000 characters) of at most 5 distinct sources, as claims citing `S1`...`S5`, and may answer `"found": false`. Sources are delimited, escaped, and declared to be data.
7. **Every claim is checked**: code checks the cited ids, a model checks that the source states the claim. One retry with the problems listed, then abstention.
8. **Models:** rewriting on `chat-medium` (local, free, about 1 s on the GPU); answers and checks on `chat-pro`.

### Measured

Steps 1 to 4 on the development set, each configuration adding one stage (`just rag-eval`, report in `evals/rag/reports/`). Recall counts distinct sources, as the model gets them:

| Configuration | Recall@1 | Recall@5 | MRR@10 | Median latency |
| -- | -- | -- | -- | -- |
| Dense only | 0.83 | 0.87 | 0.85 | 0.04 s |
| + BM25, fused by RRF | 0.63 | 0.87 | 0.74 | 0.04 s |
| + rewrite into an English query | 0.77 | 0.90 | 0.83 | 1.1 s |
| + multi-query (two variants) | 0.83 | 0.90 | 0.87 | 1.2 s |
| + explicit references pinned | 0.83 | 0.90 | 0.87 | 1.2 s |
| + rerank (the whole pipeline) | 0.73 | **1.00** | 0.85 | 1.3 s |
| Whole pipeline without BM25 | 0.77 | 0.97 | 0.86 | 1.3 s |
| Whole pipeline without rewrite | 0.70 | 0.87 | 0.77 | 0.4 s |
| Whole pipeline without multi-query | 0.77 | 0.97 | 0.85 | 1.3 s |

What the numbers say:

- **The rewrite matters most**: without it, Recall@5 falls from 1.00 to 0.87. BM25 on the French question even hurts (Recall@1 0.83 to 0.63): its French words match nothing useful in an English corpus, and RRF gives that noise the same weight as the dense ranking. Once the query is in English, BM25 brings its share back.
- **The reranker brings every expected source into the top 5** (0.90 to 1.00), which is what the model gets, but not always first (Recall@1 0.83 to 0.73). Its other use is the score: without it, the gate has nothing calibrated to decide on.
- **BM25 and multi-query** each bring one question out of 30 in the whole pipeline (0.97 to 1.00): within the noise of so small a set. They stay, cheap as they are (no model call for BM25, one rewrite for the variants), until the test set says otherwise.
- **References** change nothing here, since the development set names few articles; they guarantee that "que dit l'article 55.14" gets 55.14, which `tests/integration/test_rag.py` checks.

Abstention on the development set: at the threshold of 0.14, every question whose source was found is answered, and 5 of the 6 questions outside the corpus are refused by the gate. The sixth ("Qui a gagné le championnat 2024 ?") scores 0.9 against the articles on the championship; the model then answers "not found", since none names a champion (`tests/integration/test_rag.py`). The calibration moves from run to run, since the rewrite's variants do: an earlier run gave 0.389, because the tyre strategy question scored 0.229 instead of 0.084. Rerun on 2026-10-14 against llmops-gateway 0.5.1 (same reranker, `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` on CPU, as on the cluster): the same threshold, 0.143, and the same table but for multi-query (Recall@1 0.80, MRR@10 0.85), within one question (`evals/rag/reports/dev-2026-10-14.json`).

Latency of a question answered end to end, from the Langfuse spans: about 5 s (median of 5 questions, up to 8 s for an answer of 7 claims): rewrite 1.3 s on `chat-medium` (3.3 s for the first call, which loads the model), search 0.18 s, rerank 0.16 s, generation 1.9 s and checks 0.6 s on `chat-pro`. Generation and checks grow with the number of claims; checking the claims in parallel is the first gain if latency matters.

## Consequences

- Every stage can be switched off from the environment (`RAG_RERANK=false`...), and its effect measured with `just rag-eval`: the next corpus or model change is judged by numbers, not by a few tries.
- A question leaves one Langfuse trace with the six steps, and four scores (top rerank score, abstention and its reason, valid citations, supported claims) to follow online.
- The f1 key is limited to 60 requests and 100,000 tokens a minute, and a question makes 4 to 6 calls: every gateway call waits out a 429 until the limit resets rather than failing (`core.gateway.GatewayTransport`), and names `user: f1-rag`, so the gateway's metrics count the RAG's cost apart from the agent's and the jobs'.
- Answers cost about a tenth of a cent at Scaleway, under the gateway's monthly cap; with `RAG_ANSWER_MODEL=chat-medium` everything stays local, at the price of more "not found" answers.
- The development set is small (one question moves a recall by 3 points) and was written by the developer of the pipeline, who also tuned the rewrite prompt on it: its scores are optimistic. The test set and the harness that gates pull requests (LAB-146, LAB-148) give the numbers to quote.
- Questions spanning several seasons, or comparing two, get only the seasons they name; questions about the International Sporting Code or the technical regulations are out of the corpus and abstain.
- To revisit: when the test set shows a stage that brings nothing, it goes; when `chat-medium` answers as well as `chat-pro` on the test set, answers go local.
