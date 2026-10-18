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

# Start Qdrant, PostgreSQL, the S3 store, the API and the front (http://localhost:WEB_PORT), rebuilt when their code
# changed, wait until they are healthy, then check the gateway with the f1 key
up: _env
    docker compose up --detach --wait --build
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

# Save the Qdrant index (every collection) as snapshots in a folder, e.g. `just index-save .cache/index`: the
# evaluation CI restores them instead of indexing the corpus again
index-save dir=".cache/index":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{dir}}"
    url="${QDRANT_URL:-http://localhost:6333}"
    result() { python3 -c "import json, sys; r = json.load(sys.stdin)['result']; print($1)"; }
    for collection in $(curl -sf "$url/collections" | result "' '.join(c['name'] for c in r['collections'])"); do
        name=$(curl -sf -X POST "$url/collections/$collection/snapshots?wait=true" | result "r['name']")
        curl -sf "$url/collections/$collection/snapshots/$name" -o "{{dir}}/$collection.snapshot"
        curl -sf -X DELETE "$url/collections/$collection/snapshots/$name" > /dev/null
        echo "$collection: $(du -h "{{dir}}/$collection.snapshot" | cut -f1)"
    done

# Restore the snapshots of `just index-save` into Qdrant, replacing the collections of the same name
index-load dir=".cache/index":
    #!/usr/bin/env bash
    set -euo pipefail
    url="${QDRANT_URL:-http://localhost:6333}"
    result() { python3 -c "import json, sys; r = json.load(sys.stdin)['result']; print($1)"; }
    for file in "{{dir}}"/*.snapshot; do
        collection=$(basename "$file" .snapshot)
        curl -sf -X POST "$url/collections/$collection/snapshots/upload?priority=snapshot&wait=true" \
            -F "snapshot=@$file" > /dev/null
        echo "$collection: $(curl -sf "$url/collections/$collection" | result "r['points_count']") points"
    done

# The CI cannot build the lake (F1's live timing refuses GitHub's runners): it gets this machine's lake and Qdrant
# index, encrypted with EVAL_DATA_KEY (the repository secret of the same name), from the `eval-data` release.
# Publish the evaluation CI's data (lake and index, encrypted), then commit evals/eval-data.json, which names it
eval-data-publish: _env
    #!/usr/bin/env bash
    set -euo pipefail
    : "${EVAL_DATA_KEY:?set EVAL_DATA_KEY in .env: the repository secret of the same name}"
    work=.cache/eval-data
    rm -rf "$work" && mkdir -p "$work"
    uv run python -c 'import sys; from pathlib import Path; from core.lake import Lake; print(Lake().export(Path(sys.argv[1])), "lake files")' "$work/lake"
    just index-save "$work/index"
    asset="eval-data-$(date -u +%Y%m%dT%H%M).tar.gz.enc"
    tar -C "$work" -czf - lake index \
        | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass env:EVAL_DATA_KEY -out ".cache/$asset"
    gh release view eval-data > /dev/null 2>&1 || gh release create eval-data --prerelease --title "Evaluation data" \
        --notes "Data of the evaluation CI (docs/evaluation.md), encrypted: race data lake and FIA corpus index."
    gh release upload eval-data ".cache/$asset"
    printf '{\n "asset": "%s",\n "sha256": "%s"\n}\n' "$asset" "$(sha256sum ".cache/$asset" | cut -d' ' -f1)" \
        > evals/eval-data.json
    echo "$asset published: commit evals/eval-data.json"

# Download the data named in evals/eval-data.json, check it and decrypt it into a folder (`lake/`, `index/`)
eval-data-fetch dir=".cache/eval-data":
    #!/usr/bin/env bash
    set -euo pipefail
    : "${EVAL_DATA_KEY:?set EVAL_DATA_KEY}"
    read -r asset sha < <(python3 -c 'import json; d = json.load(open("evals/eval-data.json")); print(d["asset"], d["sha256"])')
    [ -f ".cache/$asset" ] || gh release download eval-data --pattern "$asset" --dir .cache
    echo "$sha  .cache/$asset" | sha256sum --check --quiet
    rm -rf "{{dir}}" && mkdir -p "{{dir}}"
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass env:EVAL_DATA_KEY -in ".cache/$asset" | tar -C "{{dir}}" -xzf -
    echo "{{dir}}: $(find "{{dir}}/lake" -type f | wc -l) lake files, $(ls "{{dir}}/index" | wc -l) snapshots"

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

# A strategy debrief by the agent (LAB-151), its three stops answered in the terminal:
# `just debrief "Débrief stratégique du GP d'Italie 2025 pour Ferrari"`, or `just debrief --resume <thread>`.
# Needs the stack (`just up`), the corpus and the gateway
debrief *args: _env
    uv run f1-debrief "$@"

# Evaluate a system on the dataset, one table per family: `just eval --sample 8`, `just eval --check`,
# `just eval judge-sheet`, `just eval agreement`, `just eval routing --split dev --check` (docs/evaluation.md)
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

# Serve the API with auto-reload on http://localhost:API_DEV_PORT (`just up` serves the built one on API_PORT)
api: _env
    uv run uvicorn f1.api:app --reload --port "${API_DEV_PORT:-8001}"

# Build the images locally, as the CI does: the API's, and the front's
image:
    docker build --tag f1-strategy-analyst:dev .
    docker build --tag f1-strategy-analyst-web:dev web

# Install the front's dependencies, at the pnpm version of web/package.json, and the browser of its end-to-end tests
web-install:
    cd web && corepack pnpm install --frozen-lockfile && corepack pnpm exec playwright install chromium

# Serve the front with hot reload on http://localhost:WEB_DEV_PORT, against the API of `just up` (or API_URL)
web-dev: _env
    cd web && API_URL="${API_URL:-http://localhost:${API_PORT:-8000}}" corepack pnpm dev --port "${WEB_DEV_PORT:-3001}"

# Check the front: Biome (lint and format), types, Vitest, then Playwright on a build against the API of `just up`
# (or API_URL). `just web-test unit` stops after Vitest
web-test *args: _env
    #!/usr/bin/env bash
    set -euo pipefail
    cd web
    corepack pnpm lint
    corepack pnpm typecheck
    corepack pnpm test
    [ "${1:-}" = unit ] && exit 0
    API_URL="${API_URL:-http://localhost:${API_PORT:-8000}}" corepack pnpm test:e2e

# Regenerate the front's API client from FastAPI's OpenAPI: web/openapi.json, then web/src/lib/api/schema.d.ts.
# Run it after any change to the API's routes or models, and commit both: the CI fails while they differ
web-gen-client:
    uv run python -m f1.api > web/openapi.json
    cd web && corepack pnpm gen-client

[private]
_env:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "Created .env from .env.example: change the secrets before any shared use."
    fi
