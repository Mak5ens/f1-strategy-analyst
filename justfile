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

# Start Qdrant and PostgreSQL, wait until they are healthy, then check the gateway with the f1 key
up: _env
    docker compose up --detach --wait
    @just smoke

# Stop the local services (pass --volumes to also delete the Qdrant index and the database)
down *args:
    docker compose down "$@"

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
