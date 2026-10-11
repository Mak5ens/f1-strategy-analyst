# f1-strategy-analyst

[![CI](https://github.com/Mak5ens/f1-strategy-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/Mak5ens/f1-strategy-analyst/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**An AI agent that writes sourced Formula 1 race strategy debriefs from timing data and FIA regulations, pauses for a human analyst before publishing, and is gated by an evaluation CI.**

> Status: under construction. Race data for 2024 to 2026 is ingested and the deterministic tools are in place; the FIA corpus comes next (milestone 4.1). See the [roadmap](#roadmap).

## Why

Ask *"Why did this driver lose two places at the second pit stop?"* or request the full debrief of a Grand Prix.
The agent fetches the data, computes, checks the rulebook, writes a debrief with sources, and a human analyst approves, corrects or rejects each point before it is published.

This is the **first tenant** of the [internal AI platform](#part-of-an-internal-ai-platform): every LLM call goes through the gateway with the F1 team's key and budget. It also builds the reusable foundation (agent skeleton, test set, evaluation CI) for the next tenants.

## How it works

```mermaid
flowchart LR
    q["Question or<br/>'debrief this race'"] --> data["Fetch timing data<br/>FastF1 · OpenF1 · Jolpica"]
    data --> calc["Deterministic tools<br/>gaps, stint degradation,<br/>pit loss, undercut gain"]
    calc --> rag["RAG over FIA regulations<br/>and stewards' decisions<br/>(rewrite, hybrid search, rerank)"]
    rag --> draft["Draft sourced debrief"]
    draft --> hitl{"Human analyst<br/>approve · edit · reject"}
    hitl --> pub["Published debrief"]
    draft -. "LLM calls" .-> gw["llmops-gateway<br/>(F1 team key)"]
```

- **Numbers never come from the LLM.** Lap gaps, degradation, pit loss, undercut gains and safety car periods are computed by deterministic, tested tools ([docs](docs/tools.md)). The LLM explains them.
- **Every claim is sourced**: a data point or a regulation article.
- **The agent knows when to stop.** A LangGraph interrupt pauses before publication; a PostgreSQL checkpointer lets a pending debrief resume later.

## Evaluation first

Quality is tested like code. Each pull request shows the scores and **fails below the thresholds**.

- **Test set**: 300 to 500 cases whose answer can be computed from real data, plus rulebook questions with a reference answer.
- **Tools**: promptfoo (extraction, computation, safety), Ragas (faithfulness, context recall), an LLM judge calibrated on 30 hand-graded debriefs, Langfuse Datasets for versioning.
- **Baseline**: a plain RAG is evaluated first and serves as the reference the agent has to beat.

## Stack

| Function | Tool |
| -- | -- |
| Agent | LangGraph, PostgreSQL checkpointer |
| Data | FastF1 (timing, stints, tyres, race control, weather), OpenF1 (pit stop stationary times), Jolpica-F1 (standings) |
| Data storage | Parquet in S3 (SeaweedFS locally), queried with DuckDB ([schema](docs/data-schema.md)) |
| Ingestion and RAG | LlamaIndex, Qdrant (dense and sparse vectors), reranker behind the gateway |
| Evaluation | promptfoo, Ragas, LLM judge, Langfuse Datasets |
| API and UI | FastAPI, Next.js |
| LLM access | [llmops-gateway](https://github.com/Mak5ens/llmops-gateway) |

## Quick start

Requires [just](https://just.systems/), [uv](https://docs.astral.sh/uv/) and Docker. The app calls every model through [llmops-gateway](https://github.com/Mak5ens/llmops-gateway), so start it first (`just gateway-up` in that repo).

```bash
just up           # Qdrant, PostgreSQL and the S3 store, then a check of the gateway and the data sources
just ingest 2025  # race data of a season into the lake (a few minutes; reruns skip what is stored)
just sql "SELECT driver, lap, pit_lane_time_s FROM pit_stops WHERE season = 2025 AND round = 16"
just test-unit    # unit tests, no stack needed
just api          # the API on http://localhost:8000
just down
```

`just up` creates `.env` from `.env.example` on first run. Run `just` for every recipe, and `just hooks` once to install the git hooks (ruff, mypy, gitleaks, Conventional Commits).

## Repository layout

| Path | Content |
| -- | -- |
| `src/core/` | Reusable foundation: gateway client, then retrieval, evaluation and agent graph. Never imports `f1` ([ADR-011](docs/adr/011-core-and-theme-separation.md)) |
| `src/f1/` | The Formula 1 theme: race data ingestion (`f1/data/`), deterministic tools (`f1/tools/`), prompts, API |
| `tests/unit/`, `tests/integration/` | Tests without the stack, and against it (`just smoke`) |
| `evals/` | Test set and evaluation harness (milestone 4.2) |
| `docs/adr/` | Architecture decision records of this repo |
| `docs/data-schema.md` | Tables of the race data lake, their sources and conventions |
| `docs/tools.md` | The race analysis tools: inputs, outputs, assumptions, limits |

## Roadmap

### Milestone 4: data, corpus and evaluation CI

- [ ] **4.1 Data and FIA corpus ingestion**: FastF1 / OpenF1 / Jolpica-F1 pipeline, sporting regulations and stewards' decisions indexed in Qdrant, deterministic tools with unit tests.
- [ ] **4.2 Test set and evaluation CI**: 300 to 500 cases, plain RAG baseline, promptfoo + Ragas + calibrated judge, blocking thresholds in GitHub Actions, a demo PR where a degraded prompt fails the CI. Article 4.

### Milestone 5: agent with human validation

- [ ] **5.1 LangGraph agent and human validation**: data → computation → RAG → drafting → interrupt; validation UI; deployed on the cluster behind the gateway.
- [ ] **5.2 Demo and measurements**: 2-minute video, full trace in Langfuse, agent vs plain RAG scores, share of points accepted without edits, 2 or 3 models compared on score, latency and cost per 1,000 questions. Article 5.

### Milestone 6: product front end

- [ ] **6 Visual identity and product polish**: a design system of its own, interactive race charts (gaps, positions, tyre strategy, timeline), live view of the agent's steps, public debrief pages, authentication and production hardening.

## Part of an internal AI platform

| Repo | Role |
| -- | -- |
| [llmops-gateway](https://github.com/Mak5ens/llmops-gateway) | Block 1: single entry point to LLMs, keys, budgets, anonymization, tracing |
| [llmops-platform](https://github.com/Mak5ens/llmops-platform) | Block 2: Kubernetes in GitOps, vLLM autoscaling, GPU observability, costs |
| **f1-strategy-analyst** (this repo) | Block 3: first tenant, an agent with RAG and an evaluation CI |

Write-ups coming on [maxence-labbe.fr](https://maxence-labbe.fr): article 4, *Tester une IA comme on teste du code*, and article 5, *Un agent IA qui sait s'arrêter pour demander*.

## Disclaimer

Unofficial project, not associated in any way with the Formula 1 companies. F1, FORMULA ONE and related marks are trademarks of Formula One Licensing B.V. Data comes from unofficial public sources and is used for non-commercial purposes only. No logos or brand assets are used.

## License

[MIT](LICENSE).
