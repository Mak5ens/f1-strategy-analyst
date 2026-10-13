# Questions on the rules: the retrieval pipeline

The app answers questions on the FIA rules in French ("Peut-on changer de pneus sous drapeau rouge ?") from the English corpus of `docs/corpus.md`, with every claim citing its source, or says it did not find the answer.
The pipeline is generic and lives in `core.retrieval.pipeline`; the F1 side (`f1.rag`) only brings filters, prompts and how a source is cited.
The choices and what was measured are in [ADR-024](adr/024-production-rag-pipeline.md).

```bash
just ask "Les retardataires peuvent-ils se dédoubler sous safety car en 2025 ?"
just rag-eval                    # ablation and threshold calibration on evals/rag/dev.jsonl
```

## The six steps

| Step | What it does | Model | Off with |
| -- | -- | -- | -- |
| 1. `understand` | Rewrites the question as a standalone English query, plus two variants. Code reads the filters and references in the question | `chat-medium` (local) | `RAG_REWRITE=false`, `RAG_MULTI_QUERY=false`, `RAG_REFERENCES=false` |
| 2. `search` | Hybrid search of every variant in Qdrant, dense and BM25, fused by RRF, under the season filter: 50 candidates. An explicit reference ("article 55.14") is looked up by its metadata and pinned first | `embed` | `RAG_DENSE=false`, `RAG_SPARSE=false` |
| 3. `rerank` | The gateway's cross-encoder rereads each candidate against the rewritten query | `rerank` | `RAG_RERANK=false` |
| 4. `gate` | Abstains when the best passage scores under the threshold (`RAG_THRESHOLD`, 0.14), unless the question referenced an article | none | `RAG_ABSTAIN=false` |
| 5. `generate` | Answers from the parents (whole articles, whole decisions) of the best passages scoring over the threshold, at most 5, as claims citing `S1`, `S2`... The model may answer "not found" | `chat-pro` | |
| 6. `verify` | Code: every cited id was given. Model: every claim is supported by what it cites. On failure, one more attempt with the problems listed, then abstention | `chat-pro` | `RAG_VERIFY=false` |

On llmops-platform's k3d cluster, `chat-medium` is served by `qwen2.5:0.5b` (16 GB runners, no GPU), which fails the JSON rewrite: anything running there sets `RAG_REWRITE_MODEL=chat-pro`.

`RetrievalPipeline.answer()` runs the six; `retrieve()` stops after the gate, which is what the evaluation measures.
Each step is a method that can be called alone (`understand`, `search`, `rerank`, `gate`, `sources`, `generate`, `verify`), and is tested alone in `tests/unit/test_pipeline.py`.

**Filters come from code, never from the model.** A small model asked for filters copied the example of its prompt ("Italian Grand Prix") into a question about no race, and a wrong filter hides the answer for sure. `FiaProfile.scope` reads:

- the season: a year, "cette saison", "la saison dernière"; none means the latest season, and the answer says so;
- the Grand Prix, from French names of countries, cities and circuits ("Monza", "Hongrie"): its stewards' decisions, plus the regulations, which explain them;
- references: "article 55.14", "art. 54", "B5.13".

**The rewrite must keep the subject.** The reranker and the gate read the rewritten query: against the French question, the cross-encoder gave right answers scores as low as off-topic ones (0.07 against 0.066), while the English rewrite separates them (0.20 and more, against 0.04 and less). But a rewrite can bend the question: before its prompt said otherwise, `chat-medium` turned "la règle du hors-jeu au football" into "the pit lane rule in Formula 1", and the gate let it through.

**Sources are data.** They reach the model between `<source>` tags, with `<`, `>` and quotes escaped, so a document cannot close its tag; the prompts say never to follow an instruction found in a source.

## Abstention

Three barriers, from the cheapest:

1. **The gate**, on the rerank score of the best passage. Off-topic questions (football, ticket prices, MotoGP, the budget cap, which is in the financial regulations) score 0.04 or less, a tyre strategy question 0.08 to 0.23 depending on the run.
2. **The model**, which answers `"found": false` when the sources do not answer. That is what stops "Qui a gagné le championnat 2024 ?": the reranker finds the articles on the championship very relevant (0.9), but none names a champion.
3. **The check of every claim**, which turns a draft citing an unknown source, or claiming what its source does not say, into an abstention after one retry.

The threshold is calibrated on the development set only (`just rag-eval`): the value halfway between two scores that best separates the questions whose source is in the top 5 from the others, the higher one on a tie, since abstaining is the safer error. Never calibrate on the test set (LAB-146). The last run gave 0.143: every question whose source was found scores 0.20 or more, and the off-topic ones 0.084 or less. The calibration is not stable yet: the rewrite's variants change from run to run, and an earlier run, where the tyre strategy question scored 0.229, gave 0.389, which refused a question whose article was found at rank 3 ("changer les pneus pendant que la course est suspendue", 0.20). A larger development set, and a threshold averaged over several runs, are for LAB-146 and LAB-148.

## Observability

One Langfuse trace per question, in the f1 team's project (`LANGFUSE_*` in `.env`, the keys of llmops-gateway's f1 project): a root span `rag` with the question, the configuration and the answer, and a span per step with its inputs, outputs and latency. The model calls of the trace carry its id as `session_id`, so Langfuse's session view shows the steps and the gateway's model calls (tokens, cost) together.

Scores on each trace, to follow in Langfuse's dashboards:

| Score | Meaning |
| -- | -- |
| `top_rerank_score` | Best rerank score: drifting down means questions the corpus does not cover |
| `abstained` | With the reason as comment: `nothing_found`, `below_threshold`, `not_in_sources`, `verification_failed` |
| `valid_citation_rate` | Share of claims citing only ids that were given |
| `supported_claim_rate` | Share of claims the check found supported |

Without Langfuse keys, tracing is off and the pipeline runs the same.

Every gateway call of the pipeline carries `user: f1-rag`: the gateway's Prometheus metrics (Grafana dashboard "Inference") count the cost per end user, which tells the RAG's spend from the agent's and the jobs' on the same f1 key.

## Rate limit

The f1 key allows 60 requests and 100,000 tokens a minute, and a question makes 4 to 6 calls (rewrite, embeddings, rerank, answer, one check per claim). A 429 is back-pressure, not a failure: `core.gateway.GatewayTransport` holds the call until the limit resets (LiteLLM's `reset_at` header, else `retry-after`, at most 60 s a time and 5 minutes a call), then sends it again without spending the client's retries. `just rag-eval` also spaces its questions by 3 s, so that waits do not count in the latency it measures.

## Evaluation

`evals/rag/dev.jsonl` holds 36 questions in French: 30 with the sources expected (regulations of 2024 to 2026, decisions of four Grands Prix), 6 outside the corpus. An expected source is a set of payload fields (`{"season": 2025, "parent_article": "55"}`), so it survives a new issue of the regulations. `just rag-eval` runs steps 1 to 4 under each configuration, prints Recall@1, Recall@5 and MRR@10 counted on distinct sources, as the model gets them, and writes a report in `evals/rag/reports/`.

The development set is small: one question moves a recall by 3 points. It is for calibration and for catching regressions while working; the test set and the harness that gates pull requests are LAB-146 and LAB-148.
