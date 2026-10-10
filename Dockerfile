# Image of the app's API, built and signed by llmops-platform's shared workflow (.github/workflows/images.yml).
# Two stages: uv installs the locked dependencies and the app into a virtualenv, and the runtime stage only copies
# that virtualenv, without uv, the build cache or the sources.

FROM python:3.12.15-slim-trixie AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /bin/uv

# Compile bytecode once at build time, and copy files out of the cache: the cache mount is not in the image.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# Dependencies first, in a layer of their own: it is only rebuilt when uv.lock changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.12.15-slim-trixie

# A fixed non-root user, so Kubernetes can enforce runAsNonRoot.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER 10001
EXPOSE 8000

# No HEALTHCHECK: Kubernetes probes /healthz.
CMD ["uvicorn", "f1.api:app", "--host", "0.0.0.0", "--port", "8000"]
