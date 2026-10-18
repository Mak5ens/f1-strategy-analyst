# The front

A Next.js app in `web/` (LAB-187; the choices in [ADR-026](adr/026-nextjs-front-in-the-app-repo.md)). The race is the entry point: a calendar of the seasons in the data, a page per Grand Prix, its debriefs; the analyst's screens come with LAB-152. Design direction in [design.md](design.md).

```bash
just up               # the API on :8000 and the front on http://localhost:3000, built from their Dockerfiles
just web-install      # once: the front's dependencies (pnpm through corepack) and Playwright's Chromium
just web-dev          # the front with hot reload on :3001, against the API of `just up`
just web-test         # Biome, types, Vitest, then Playwright against the API (`just web-test unit` stops before)
just web-gen-client   # after any change to the API's routes or models
```

Node.js 24 and corepack are needed on the host for `web-dev`, `web-test` and `web-gen-client`; `just up` only needs Docker.

## Pages

| Route | Content |
| -- | -- |
| `/` | The home page: a request for a debrief, the last race and two others, the requests waiting, the season's calendar (`?saison=2024`), the last debriefs |
| `/en-attente` | The requests waiting for the analyst, `?arret=plan` for one stop |
| `/debriefs/<id>` | A request where it stands: the agent's question, the plan to tick (by driver), the review point by point (approve, correct, reject, a reason for the last two), the agent at work or stopped, or the debrief published with its figures, sources and the drivers' tyre strategy |
| `/debriefs` | The published debriefs, `?saison=2025&manche=16` |
| `/journal` | Every review decision with the agent's text, `?action=reject`, `?debrief=<id>` |
| `/grand-prix` | The calendar of a season (`?saison=2024`), a card per round with its winner (LAB-202) |
| `/grand-prix/<season>/<round>` | A Grand Prix: result, grid, tyre strategies and stops, standings after the round, safety cars and penalties, then its debriefs (LAB-202) |

A race's page is read from the lake by `f1.grand_prix.GrandPrix` (`GET /races/{season}/{round}`), with the analysis tools' own functions (`pit_stop_loss`, `neutralizations`, `penalties`): no model is called. A round the lake does not have says so; a round whose race is not run yet shows its header without results. The CI has no race data: its end-to-end tests serve the synthetic season of `tests/unit/test_grand_prix.py`.

The three stops answer through server actions (`src/app/actions.ts`): the agent runs inside the call, up to a minute from the plan to the review, then the page is rendered again where the request stands. Each review decision is logged with the agent's text (`decisions` table, `GET /decisions`); `just eval-dataset review-candidates` turns the corrections and rejections for a wrong number or source into candidate cases (`evals/datasets/candidates/review.jsonl`) to complete by hand.

`e2e/review-flow.spec.ts` runs the whole path through the real agent and models: only with `E2E_AGENT=1` (a few cents a run), against `just up` and the gateway; the CI skips it.

## Calling the API

The pages are server components: the front's server calls the API on `API_URL` (the `api` service of compose.yaml), and the browser only talks to the front. Calls go through `apiClient()` (`web/src/lib/api/client.ts`), an openapi-fetch client typed by `schema.d.ts`, which openapi-typescript generates from `web/openapi.json`, FastAPI's document (`uv run python -m f1.api`).

After a change to a route or a model of `src/f1/api.py`, run `just web-gen-client` and commit `web/openapi.json` and `web/src/lib/api/schema.d.ts` with it. Otherwise:

- `tests/unit/test_api.py` fails: the API no longer matches `web/openapi.json`;
- the `Web` workflow fails: the schema is not generated from `web/openapi.json`, or a page no longer type-checks against it.

## Layout

| Path | Content |
| -- | -- |
| `src/app/` | Routes (App Router), the layout and `globals.css`, the design tokens |
| `src/components/ui/` | shadcn/ui components, copied in (`pnpm dlx shadcn@4.21.0 add <name>`): ours to restyle |
| `src/components/` | The app's components, each with its Vitest test |
| `src/lib/api/` | The generated schema and the client |
| `src/messages/fr.ts`, `src/lib/i18n.ts` | Every text of the interface, in French, read through `getMessages()` |
| `e2e/` | Playwright tests, against a build and a running API |

## Conventions

- **No text inline**: a component reads its texts from `getMessages()`. A second language is a file of the same type as `fr.ts`.
- **No colour inline**: components use the tokens (`bg-background`, `text-muted-foreground`, `bg-success`...), defined once in `globals.css` with their light and dark values.
- **Dynamic pages say so**: a page showing the state of now calls `await connection()` before reading the API, so Next.js does not render it at build time.
- **Versions are exact**, published at least two weeks before they are pinned; Renovate proposes the updates. Biome's version is the same in `package.json` and `.pre-commit-config.yaml` (grouped by Renovate).
