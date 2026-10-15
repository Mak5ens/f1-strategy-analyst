# Image of the front, built and signed by llmops-platform's shared workflow (.github/workflows/images.yml), as the
# API's. Two stages: pnpm installs the locked dependencies and builds Next.js as a standalone server, and the runtime
# stage only copies that server (.next/standalone, with the static files `pnpm build` puts in it), without pnpm,
# the dependencies of the build or the sources.

FROM node:24.21.0-trixie-slim AS build

# pnpm at the version of package.json's packageManager, through corepack, without asking.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /src
RUN corepack enable

# Dependencies first, in a layer of their own: it is only rebuilt when pnpm-lock.yaml changes.
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

COPY . .
RUN pnpm build


FROM node:24.21.0-trixie-slim

# A fixed non-root user, so Kubernetes can enforce runAsNonRoot; the same uid as the API's image.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=build --chown=10001 /src/.next/standalone ./

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

USER 10001
EXPOSE 3000

# No HEALTHCHECK: Kubernetes probes the port. API_URL, where the server reaches the API, is set at run time.
CMD ["node", "server.js"]
