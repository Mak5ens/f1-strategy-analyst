# ADR-011: A reusable core and a theme, in two packages of one repo

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Block 3 of the platform plans three client apps in Linear: the F1 strategy analyst, a game master assistant for D&D, and a residential lease checker.
All three need the same foundation: a client of the gateway, a production retrieval pipeline (query rewriting, hybrid search, reranking, abstention), an evaluation harness that gates pull requests, and an agent graph that stops for a human.
What differs is the domain: data, deterministic tools, documents, prompts and screens.
F1 is built first, so its repo sets the conventions the next two copy (ADR-010: one repo per app).
If the foundation is written with F1 vocabulary inside, the second app starts with a rewrite instead of a copy.

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. Two packages in this repo, `core` and `f1`, with a dependency rule checked by a test | No release process to maintain yet; one PR changes both sides while the foundation is still taking shape; the rule keeps `core` copyable | The next themes copy `core` instead of depending on a version; copies can drift |
| B. A shared library repo published as a package, used by every theme | One versioned source of truth; fixes reach every theme | A second repo and a release cycle before the first app even works; the API of `core` would be frozen before two real uses have shaped it |
| C. No separation: write F1 code, extract the foundation when the second theme starts | Fastest start | Extraction means untangling F1 assumptions spread everywhere, with no test to say when it is done |

## Decision

We choose **A**.
`src/core/` holds the foundation and `src/f1/` the theme, both shipped in the `f1-strategy-analyst` distribution.
The rules:

- `f1` may import `core`; `core` never imports `f1`. `tests/unit/test_architecture.py` parses every module of `core` and fails on any import of `f1`, whatever its form (top level, `from` import, inside a function).
- `core` holds no domain vocabulary: no drivers, seasons or FIA articles. The theme passes what is specific to it (prompts, metadata filters, tool catalog) as parameters or settings.
- Platform conventions are not domain vocabulary: `core` may know the gateway's usage aliases (`chat-small`, `embed`), since every team of the platform uses them.
- Settings come from the environment. `core` reads its own (`GATEWAY_*`), and never a theme's.

## Consequences

- The D&D and lease apps start by copying `src/core/`, its tests and this ADR, then write their own theme package.
- A fix made in `core` after a copy has to be brought to the other repos by hand. We accept it for now.
- We revisit this when the second theme starts: if its copy of `core` already needs changes, we extract `core` into its own published package (option B), shaped by two real uses instead of one.
