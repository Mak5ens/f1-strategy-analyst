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
| `/` | The home page: a free question and its answer (`?question=<id>`, LAB-206), the recent questions, the last race and two others, the requests waiting, the season's calendar (`?saison=2024`), the last debriefs |
| `/en-attente` | The requests waiting for the analyst, `?arret=plan` for one stop |
| `/debriefs/<id>` | A request where it stands: the agent's question, the plan to tick (by driver), the review point by point (approve, correct, reject, a reason for the last two), the agent at work or stopped, or the debrief published with its figures, sources and the drivers' tyre strategy |
| `/debriefs` | The published debriefs, `?saison=2025&manche=16` |
| `/journal` | Every review decision with the agent's text, `?action=reject`, `?debrief=<id>` |
| `/saison` | A season told by its numbers (`?saison=2025`, the latest by default, LAB-215): the leader, the rounds raced, the leading team and the driver in form; the championship of drivers or teams after each round (the first five highlighted, read round by round with the keyboard); every driver's result round by round, each round a link to its race; the teams' pace in qualifying and in the race, round by round and their season's median. The definitions are in `docs/tools.md` |
| `/duel` | Two drivers face to face over a season (`?saison=2025&a=LEC&b=HAM`; the leader and a teammate by default, LAB-212): who was ahead how often in qualifying and in the race, the points, the median gaps, the qualifying and pace gaps round by round, a table linking each race's « Course » tab with both drivers highlighted. The definitions are in `docs/tools.md` |
| `/grand-prix` | The calendar of a season (`?saison=2024`), a card per round with its winner (LAB-202) |
| `/grand-prix/<season>/<round>` | A Grand Prix: result, grid, the race lap by lap (positions and gaps, LAB-189), tyre strategies and stops, standings after the round, safety cars and penalties, then its debriefs (LAB-202) |

A race's page is read from the lake by `f1.grand_prix.GrandPrix` (`GET /races/{season}/{round}`), with the analysis tools' own functions (`pit_stop_loss`, `neutralizations`, `penalties`): no model is called. Its « Course » tab reads `GET /races/{season}/{round}/laps`: each driver's position, gap to the leader at the line, lap time and tyres, lap by lap. The charts (`src/components/race/race-charts.tsx`, ADR-026) draw the positions from the grid and the gaps to the leader or to a chosen driver, the difference of two drivers' gaps to the leader, as the `gaps` tool computes it (`tests/unit/test_grand_prix.py` checks they are equal); stops and neutralizations are marked, the podium highlighted, any driver added from the list. The pace chart shows each stint's clean laps and the line the `degradation` tool fits on them (`f1.tools.degradation.fit`, shared by the tool and the page), with the tool's degradation per stint in a table. The chronology lists the safety cars, VSCs, red flags and penalties in lap order, each linked to its FIA text: the article of the season's sporting regulations at its page of the PDF, or the stewards' decision that gave the penalty, with the articles it cites. `f1.race_rules.RaceRules` finds them by code in the FIA index (titles, then driver and seconds); an event it cannot find says so, and an index out of reach leaves the events without links. A lap is read by hovering a chart or an event, a tap, or the arrow keys (each chart is a slider over the laps), in every chart at once; a table gives the same numbers.

The « Simulateur » tab moves a driver's stops (a slider per stop), changes a stint's compound (a list per stint, LAB-214), and projects the race again at every change (the `simulate` server action, `src/components/race/strategy-simulator.tsx`): race time won or lost, finishing place and gap to a rival as raced and projected, and both gaps lap by lap. Every projection shows the error measured on real stints extended as much, or projected from another compound, the laps beyond the tyre ages measured, and what the model ignores. A difference smaller than the error is said not to conclude.

A debrief's point opens the chart of the numbers it cites (« Voir sur le graphique »), in the review and once published: each analysis the API returns (`Fact.chart`) names its chart, read by code from the tool (`f1.charts.chart_for`): a gap or a pit cycle shows the gaps to the other driver, zoomed on its laps (a cycle with 3 laps on each side), tyres the pace, stops the positions; any other analysis has none. A link opens the whole race on the GP page with the point's drivers highlighted (`?onglet=course&pilotes=LEC,PIA`). A round the lake does not have says so; a round whose race is not run yet shows its header without results. The CI has no race data: its end-to-end tests serve the synthetic season of `tests/unit/test_grand_prix.py`.

The three stops answer through server actions (`src/app/actions.ts`): the agent runs inside the call, up to a minute from the plan to the review, then the page is rendered again where the request stands. Each review decision is logged with the agent's text (`decisions` table, `GET /decisions`); `just eval-dataset review-candidates` turns the corrections and rejections for a wrong number or source into candidate cases (`evals/datasets/candidates/review.jsonl`) to complete by hand.

The free question goes to `POST /questions` through the `askFree` action: a debrief opens its request, any other answer is shown under the field (`src/components/ask/`), with its FIA passages or the analyses its numbers come from, and a link to the race's page. When the API asks which path or which race, each choice sends the question again with it (`route`, `season`, `round`).

`e2e/free-question.spec.ts` asks a rule question and one the analyst must route; `e2e/review-flow.spec.ts` runs the whole path through the real agent and models. Both run only with `E2E_AGENT=1` (a few cents a run), against `just up` and the gateway; the CI skips it.

## Calling the API

The pages are server components: the front's server calls the API on `API_URL` (the `api` service of compose.yaml), and the browser only talks to the front. Calls go through `apiClient()` (`web/src/lib/api/client.ts`), an openapi-fetch client typed by `schema.d.ts`, which openapi-typescript generates from `web/openapi.json`, FastAPI's document (`uv run python -m f1.api`).

After a change to a route or a model of `src/f1/api.py`, run `just web-gen-client` and commit `web/openapi.json` and `web/src/lib/api/schema.d.ts` with it. Otherwise:

- `tests/unit/test_api.py` fails: the API no longer matches `web/openapi.json`;
- the `Web` workflow fails: the schema is not generated from `web/openapi.json`, or a page no longer type-checks against it.

## Accounts

The site uses LabbTech Auth (LAB-192), the SSO of every LabbTech app (`labbtech-universe`: `apps/auth` for the pages, `backends/auth-api` for the tokens), with Google sign-in. It is not an OAuth client flow: the SSO sets two httpOnly cookies on its whole domain (`Domain=.labbtech.fr` in production, the host `localhost` locally, every port included), `auth_token` (an RS256 JWT, 15 minutes) and `refresh_token` (30 days). The site must therefore be served under that domain.

| Who | Reads | Does |
| -- | -- | -- |
| A visitor, with or without an account | The races, the season, the duels, the simulator, the published debriefs and their questions | Nothing that calls a model |
| An analyst (`AUTH_ANALYSTS`) | Also the requests in progress, the free questions and the journal | Asks, starts a debrief, answers its stops, asks on a debrief |

- **The API decides** (`core.auth`): it checks the token's signature against the SSO's public keys (`AUTH_JWKS_URI`, cached), its issuer, audience and expiry, on every call; analyst routes answer 401 without an account, 403 for another one, and a request not yet published does not exist for a reader (404). Analysts are named by account id, not email: the SSO lets an account sign in before confirming its email. Without `AUTH_JWKS_URI` the API is open, every caller the local analyst: the default locally and in CI.
- **The front forwards and hides**: `apiClient()` sends the cookie's token as a Bearer header; `fetchSession()` (`GET /me`, once per request) tells the header and the pages who is there. `AnalystOnly` replaces a form with a sign-in invitation, `ReservedPage` replaces `/en-attente` and `/journal`; the header hides those sections.
- **Renewal**: `src/proxy.ts` calls the SSO's `/auth/refresh` before a page renders when the token is missing or has less than a minute left, and passes the new cookies to the browser and to the page's own calls. An SSO that does not answer deletes nothing.
- **Sign-in and sign-out**: `/connexion?retour=<path>` sends the visitor to the SSO's page, which sends them back to that path of `APP_URL` (a path of this site only). `/deconnexion` (a form's POST) revokes the session on the SSO, for every LabbTech app.
- **Google**: the SSO sends a visitor back after Google only to an origin of its `CORS_ALLOWED_ORIGINS`: the site's address must be there.

Locally: `just auth-up` in labbtech-universe, then the `AUTH_*` and `APP_URL` lines of `.env.example`.

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
