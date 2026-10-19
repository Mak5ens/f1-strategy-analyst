# ADR-026: The front is a Next.js app in `web/`, calling the API through a client generated from its OpenAPI

- **Status:** Accepted
- **Date:** 2026-10-15

## Context

The app needs a real product front, deployable on the cluster, not a demo page (LAB-187). Its first job is the analyst's work on a debrief (LAB-152): a request, the clarification to choose, the plan to tick, every point to approve, correct or reject with a reason, then the published debriefs. A request waits for a person for minutes or days, so the screens read the state of the agent at each visit (`Agent.get`), and answer it (`Agent.resume`). Milestone 6 then adds race charts (gaps, positions, tyre strategy), a live view of the agent's steps and public debrief pages: the front is meant to become a polished product, not an admin screen.

Constraints and facts:

- The API is FastAPI, which writes an OpenAPI 3.1 document of every route and model. The API and its screens change together: LAB-152 adds the routes and the pages that use them in the same piece of work.
- The terminal driver of LAB-151 (`just debrief`) already answers the three stops: the front adds no logic of its own to the agent, it shows and sends what the API gives.
- One person writes both sides; the Python side already has its linting, types, tests and image pipeline (llmops-platform's shared workflow: Trivy, SBOM, cosign).
- Next.js 16 removed `next lint`: lint and format need a tool of their own.

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. Next.js (App Router), server components calling the API from the front's server | React's ecosystem for the charts and components of milestone 6 (shadcn/ui, Recharts, visx); pages rendered on the server, so public debrief pages are indexable; the front's server is where the API is called, so the API's address and later its credentials never reach the browser; a standalone build runs as one Node.js process | A Node.js server to run and patch next to the API; the framework moves fast (caching changed between 14, 15 and 16) |
| B. HTMX with Jinja templates served by FastAPI | One language, one process, one image; no build | Interactive views (a chart following the race, the review of twelve points, a live view of the agent's steps) end up as hand-written JavaScript; no component ecosystem to build a product on |
| C. React + Vite, a single-page app served as static files | Simple to build and host; the same React ecosystem | Everything rendered in the browser: public debrief pages are empty to a crawler, the browser calls the API directly (CORS, the API's address in the bundle, credentials in the browser later) |
| D. SvelteKit | Lighter runtime, pleasant to write | Smaller ecosystem of charts and components; shadcn/ui exists only as a port |
| E. Astro | Fast, content-first pages | Built for content sites: the review screens, which are application state, would live in islands of another framework |

And where the front lives:

| Option | Pros | Cons |
| -- | -- | -- |
| 1. `web/` in this repo | One PR changes a route and the page that uses it; the generated client is checked against the API of the same commit | Two toolchains in one repo (uv and pnpm), two images |
| 2. A repo of its own | Separate releases and CI | The client is generated from a published API document, so the two drift between releases; a change spans two PRs (ADR-010 already keeps one repo per app) |

## Decision

We choose **A** and **1**:

1. **Next.js 16, App Router, TypeScript strict** (`noUncheckedIndexedAccess`), in `web/`. Pages are server components that call the API from the front's server (`API_URL`, the `api` service of compose.yaml); the browser only talks to the front. A page that shows the state of now calls `connection()`, so it is not frozen at build time.
2. **The API client is generated, never written**: `just web-gen-client` writes FastAPI's document to `web/openapi.json`, then openapi-typescript writes `web/src/lib/api/schema.d.ts`; openapi-fetch types every call with it. Both files are committed. A route or a model changed without regenerating fails twice: `tests/unit/test_api.py` compares the API with `web/openapi.json` (ci.yml, on every PR), and the `Web` workflow regenerates the schema and fails on any difference, then type-checks the pages against it. The OpenAPI document carries the version of the contract (`0.1.0`), not the app's, which release-please bumps on every release.
3. **pnpm**, its version pinned by `packageManager` (corepack locally, `pnpm/action-setup` in CI). **Biome** for lint and format: one binary, no plugin chain; its pre-commit hook installs its own copy, so `just lint` needs no `pnpm install`. **Vitest** for components and the client, **Playwright** for the pages against a running API.
4. **Tailwind CSS 4 and shadcn/ui**: the components are copied into `web/src/components/ui/`, so they are our code to restyle. Colours are tokens on `:root` (`globals.css`), each with its light and dark value (`light-dark()`), following the system's theme; milestone 6 replaces the values, not the components.
5. **French first, translation ready**: every text in `web/src/messages/fr.ts`, whose type a second language must match, read through `getMessages()`; `<html lang>` from `locale`. No i18n library until a second language exists.
6. **Images and stack**: `web/Dockerfile` builds the standalone server and runs it as uid 10001, like the API's image; `images.yml` builds and signs it with the shared workflow (`ghcr.io/mak5ens/f1-strategy-analyst/web`). `just up` builds and runs the API and the front in compose next to their dependencies; `just api` and `just web-dev` reload on ports of their own (8001, 3001).
7. **Charts without a library** (LAB-189): the race charts are SVG drawn by React components, their series, scales and ticks plain functions of `web/src/lib/race-chart.ts`. visx or D3 would bring scales and shapes we write in a few lines, ECharts a canvas of its own styling and about a megabyte; neither knows our tokens. Drawn by hand, a chart takes the team colours and the theme's tokens like any component, renders on the server, adds nothing to the bundle, and its values are tested exactly against the tools' outputs. To revisit if a chart needs zoom with inertia or thousands of points.
8. **Versions**: exact versions, each published at least two weeks before it is pinned, then followed by Renovate. TypeScript stays on 5.9: openapi-typescript 7.13 declares `typescript ^5`, and TypeScript 7 is the native compiler.

## Consequences

- `just up` serves the front on port 3000; its home page reads `/info` through the generated client and shows the version of the API (`tests/integration/test_stack.py`, and `web/e2e/home.spec.ts` in CI against the API of the commit).
- A change of the API's contract is visible in the PR: the diff of `web/openapi.json` and of the generated schema, next to the pages it breaks.
- Two toolchains and two images to keep up to date: 168 npm packages in `pnpm-lock.yaml`, a 388 MB front image on `node:24-trixie-slim`. A distroless Node.js base would shrink it; to revisit when the image is deployed (LAB-153).
- The `Web` workflow only runs when `web/` changes: an API change alone is caught by the Python unit test, and fixing it changes `web/`.
- Next.js's caching defaults change between major versions: pages say explicitly when they are dynamic (`connection()`), and a major upgrade waits for a reading of its notes (Renovate's dashboard approval).
- To revisit if the front stays a set of forms after milestone 6 (HTMX would then cost less), or if the API gets other clients than this front (the client would then be generated from a published document).
