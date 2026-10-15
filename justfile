# Load .env so recipes see the ports and the gateway settings.
set dotenv-load
# Pass recipe arguments as "$@", so a quoted argument like `-k "not chat"` stays one argument.
set positional-arguments

# List recipes
default:
    @just --list

# Install the git hooks (pre-commit and commit-msg)
hooks:
    uvx pre-commit install

# Run every pre-commit check on all files (whitespace, YAML, Markdown, gitleaks, ruff, mypy)
lint:
    uvx pre-commit run --all-files

# Start Qdrant, PostgreSQL and the S3 store, wait until they are healthy, then check the gateway with the f1 key
up: _env
    docker compose up --detach --wait
    @just smoke

# Stop the local services (pass --volumes to also delete the Qdrant index, the database and the race data)
down *args:
    docker compose down "$@"

# Ingest race data into the lake, e.g. `just ingest 2025`, `just ingest 2024 2025 2026`, `just ingest 2025 --round 16`.
# Rounds already stored are skipped; add --force to rewrite them
ingest *args: _env
    uv run f1-ingest "$@"

# Index the FIA corpus in Qdrant, e.g. `just corpus 2025` or `just corpus 2024 2025 2026 --regulations-only`.
# The first run downloads every document (10 s apart, as fia.com asks); reruns only embed what changed
corpus *args: _env
    uv run f1-corpus "$@"

# Ask a question on the FIA rules, in French: `just ask "Peut-on changer de pneus sous drapeau rouge ?"`.
# Needs the corpus (`just corpus`) and the gateway; the trace goes to the f1 project in Langfuse
ask question: _env
    uv run f1-ask "$1"

# Measure the retrieval pipeline stage by stage on evals/datasets/dev.jsonl and calibrate the abstention threshold
# (about 20 minutes; `just rag-eval --only "+ rerank"` for one configuration). Report in evals/rag/reports/
rag-eval *args: _env
    uv run f1-rag-eval "$@"

# The reference system (LAB-147): dense search, tools, answer, e.g. `just baseline "Combien de temps Norris a-t-il perdu à son arrêt à Monza en 2025 ?"`
baseline question: _env
    uv run f1-baseline "$1"

# Evaluate a system on the dataset, one table per family: `just eval --sample 8`, `just eval --check`,
# `just eval judge-sheet`, `just eval agreement` (docs/evaluation.md)
eval *args: _env
    uv run f1-eval "$@"

# Build the evaluation dataset (evals/datasets/): `just eval-dataset`, `check`, `push` (Langfuse), `draft-regulation`
eval-dataset *args: _env
    uv run f1-eval-dataset "$@"

# Summarize every session of a season through the platform's job queue, e.g. `just season-jobs 2025 --simulate`
# (needs llmops-gateway's stack: RabbitMQ and the worker)
season-jobs season *args: _env
    uv run f1-season-jobs "$@"

# Query the lake with DuckDB SQL, e.g. `just sql "SELECT * FROM results WHERE season = 2025 AND round = 16"`
sql query: _env
    uv run python -c 'import sys; from f1.data import connect; connect().sql(sys.argv[1]).show(max_rows=100)' "$1"

# Follow the logs of the local services
logs:
    docker compose logs --follow

# Check the stack: the gateway answers the f1 key (chat and embeddings) and Qdrant is ready
smoke: _env
    uv run pytest tests/integration -q

# Run every test; pass pytest arguments, e.g. `just test -k gateway`. Integration tests need `just up`
test *args: _env
    uv run pytest "$@"

# Unit tests only: no stack, a few seconds
test-unit *args:
    uv run pytest tests/unit "$@"

# Serve the API with auto-reload on http://localhost:API_PORT
api: _env
    uv run uvicorn f1.api:app --reload --port "${API_PORT:-8000}"

# Build the app image locally, as the CI does
image:
    docker build --tag f1-strategy-analyst:dev .

[private]
_env:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "Created .env from .env.example: change the secrets before any shared use."
    fi
