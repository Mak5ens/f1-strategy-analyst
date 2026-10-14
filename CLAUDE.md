# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

`f1-strategy-analyst` is block 3 of a portfolio "internal AI platform", and its first client app: an agent that writes sourced Formula 1 race strategy debriefs from timing data and FIA regulations, and stops for a human analyst before publishing. Every model call goes through `llmops-gateway` with the `f1` team's key. The user cares about F1 beyond the portfolio: the front end is meant to become a polished product.

Planning lives in Linear (team key `LAB`, project "Plateforme IA · Analyste stratégie F1", milestones 4.1 to 6).

## Design principles (decided 2026-10-10, see the Linear issues)

- Numbers never come from the LLM: deterministic, unit-tested tools compute them (LAB-144), and the agent's `verify` node checks every number and source of a draft.
- Production retrieval (LAB-186): query rewriting (French questions, English FIA corpus), hybrid dense + sparse search with RRF, reranking through the gateway's `rerank` alias, an abstention threshold, citation checks. Each stage can be switched off to measure its gain (ablation). LAB-147 is a deliberately naive baseline.
- The agent is a fixed LangGraph graph, not a free ReAct agent: the LLM only fills bounded nodes with validated structured output, and code does the routing. Three human stops: clarification, plan validation, point-by-point review with a reason for every rejection.
- The app speaks French; the corpus stays in English.

## Layout and rules

- `src/core/`: the reusable foundation; `src/f1/`: the theme. `core` never imports `f1` and holds no F1 vocabulary (ADR-011); `tests/unit/test_architecture.py` enforces the import rule.
- `core.gateway.gateway_client()` is the only way to reach a model, reranking included. Settings come from `GATEWAY_URL` and `GATEWAY_API_KEY` (the team's virtual key, never the master key). Its transport (`GatewayTransport`) waits out the key's rate limit (60 requests and 100,000 tokens a minute) on a 429, until LiteLLM's `reset_at`, and names the app as `user` for the gateway's cost per end user (`f1-rag` for the RAG). The OpenAI SDK 3 runs on `httpx2`: its transports and test mocks are `httpx2` ones.
- Race data (LAB-143): every session of a weekend (`FP1`-`FP3`, `SQ`, `Q`, `S`, `R`, since schema 3); always filter on `session`. `src/f1/data/` ingests FastF1, OpenF1 and Jolpica-F1 into Parquet files on S3 (`core.lake.Lake`, SeaweedFS locally), queried with DuckDB through `f1.data.connect()`. Tools read the lake, never the APIs. Schema in `src/f1/data/schema.py`, documented in `docs/data-schema.md`: bump `SCHEMA_VERSION` on a breaking change. A round is written then marked by `_manifest/<season>/<round>.json`; reruns skip marked rounds.
- Tools (LAB-144): `src/f1/tools/`, one module per tool, each a `core.tools.Tool` (Pydantic input and output, JSON schema for tool calling), bound to the lake by `f1.tools.catalog(RaceData(connect()))`. A request the data cannot answer raises `core.tools.ToolError`, never a guessed number. Assumptions and limits in `docs/tools.md`; reference races in `tests/integration/test_tools_reference.py`.
- FIA corpus (LAB-145): `src/f1/corpus/` downloads the sporting regulations (last issue per season) and the stewards' decisions from fia.com (10 s between requests, as its robots.txt asks; cache in `.cache/fia/`, never committed), parses them by structure (article or section -> paragraphs; decision -> summary and reasons) and syncs them into Qdrant through `core.retrieval.index.HybridIndex` (`fia_chunks` with `dense` and `bm25` vectors, `fia_parents`). Only chunks whose content hash changed are embedded. Details and limits in `docs/corpus.md`.
- Retrieval pipeline (LAB-186): `core.retrieval.pipeline.RetrievalPipeline`, six traced steps (understand, search, rerank, gate, generate, verify), switches and models in `PipelineConfig` (`RAG_*` env). The theme gives a `Profile` (`f1.rag.profile.FiaProfile`): filters and references are read by code, never by the model; reranking reads the English rewrite, so the rewrite prompt must keep the question's subject. Rewriting runs on `chat-medium`, answers and checks on `chat-pro` (gateway LAB-185); `chat-small`/`chat-large` cannot follow the JSON schemas. `just ask`, `just rag-eval` (ablation and threshold calibration on `evals/rag/dev.jsonl`, never the test set). Details in `docs/rag.md`, choices in ADR-024. Tracing: `core.tracing` (Langfuse, f1 project keys `LANGFUSE_*`, off without keys).
- Session summary jobs (LAB-196): `core.jobs.run_batch` publishes jobs to llmops-platform's RabbitMQ (exchange `jobs`, key `inference`, format in llmops-gateway/worker/README.md) and collects replies on a durable queue, or finds failed jobs in `jobs.inference.dead`. `f1.jobs.facts` computes each session's facts from the lake, drivers in full names (a model expands codes wrongly); `f1.jobs` checks every number and name of a summary against them. `just season-jobs 2025 [--simulate]`. Details in `docs/jobs.md`.
- `compose.yaml` only runs Qdrant, PostgreSQL and the S3 store (SeaweedFS on port 8334, since llmops-gateway's Langfuse holds 8333). The gateway runs from `../llmops-gateway` (`just gateway-up` there), and the app runs on the host with `uv run` during development.
- The front end will be Next.js in `web/` (LAB-187), with an API client generated from FastAPI's OpenAPI.

## Commands

Tasks run with [just](https://just.systems/) (`justfile`, which loads `.env`); there is no Makefile. Run `just` to list recipes.

- `just up`: start Qdrant, PostgreSQL and the S3 store, wait until healthy, then run `just smoke`. Creates `.env` from `.env.example` if missing.
- `just smoke`: `tests/integration/`, against the stack and the running gateway (chat, embeddings, model list of the `f1` key, Qdrant, S3), plus the real data sources: the 2025 Italian GP checked against official results and Jolpica-F1 (needs the network).
- `just corpus 2025` (or `2024 2025 2026`, `--regulations-only`, `--decisions-only`, `--refresh`): FIA corpus into Qdrant; needs the gateway for embeddings.
- `just season-jobs 2025` (`--round 16`, `--simulate`): one summary job per session through the job queue; needs llmops-gateway's stack.
- `just ask "<question>"`: a question on the FIA rules, answered with sources; `just rag-eval`: retrieval ablation and threshold calibration (about 20 minutes).
- `just ingest 2025` (or `2024 2025 2026`, `--round 16`, `--force`): race data into the lake; `just sql "<query>"` queries it.
- `just test-unit`: unit tests, no stack, under a second. `just test` runs everything, with pytest arguments passed through.
- `just api`: the FastAPI app with auto-reload.
- `just image`: build the Docker image as the CI does.
- `just lint`: every pre-commit hook (whitespace, YAML, Markdown, gitleaks, ruff, mypy strict on `src` and `tests`).
- `just down`: stop the services; `just down --volumes` also deletes the Qdrant index, the database and the lake.

## CI and releases

`.github/workflows/ci.yml` runs pre-commit, a full-history gitleaks scan, the unit tests and the PR title check (PRs are squash-merged). The integration tests do not run in CI yet: they need the gateway stack. `.github/workflows/images.yml` runs release-please and builds the image with llmops-platform's shared workflow (Trivy, then on main: GHCR, SBOM, cosign), pinned to a commit of its main branch. `CHANGELOG.md` is written by release-please: never edit it by hand.

## Conventions

- Branch names come from Linear issues: `feature/lab-<n>-<slug>`.
- Commits follow Conventional Commits, enforced by a commit-msg hook. No Claude attribution in commits or PRs.
- ADRs specific to this repo go in `docs/adr/`. ADR numbers are global to the portfolio: 011 here, 012 and 013 planned for F1, 024 (RAG), 025 (agent) and 026 (front end) reserved. Check Linear before taking a new number.
- Public repo: public data only. FIA documents are downloaded, never committed. No F1, FIA or team logos, fonts or brand assets.
