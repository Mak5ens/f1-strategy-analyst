# The debrief agent

The agent writes a strategy debrief of a Grand Prix, for the race, a driver or a team, and stops three times for an analyst: a clarification instead of a guess, the plan before any analysis runs, and the review of every point before anything is published (LAB-151; the choices in [ADR-025](adr/025-controlled-agent-graph.md)).

```bash
just debrief "Débrief stratégique du GP d'Italie 2025 pour Ferrari"
just debrief --resume <thread>                      # a request waiting, after a restart
just debrief --resume <thread> --answer '["result", "stops:LEC"]'   # one answer as JSON
```

It needs the stack (`just up`: PostgreSQL keeps the requests), the lake, the FIA corpus and the gateway.

## The graph

```text
parse ─▶ resolve ─▶ plan ─▶ ⏸ approve_plan ─▶ run_tools ─▶ detect_events ─▶ retrieve_rules ─▶ draft ─▶ verify
           │  ▲                                                                                  ▲        │
           ▼  │                                                                                  └────────┤ problems, 3 drafts at most
        ⏸ clarify                                                                                          ▼
                                                                    publish ◀─ apply ◀─ ⏸ review ◀─────────┘
```

| Node | Who | What |
| -- | -- | -- |
| `parse` | code + model | Code reads the season and the Grand Prix, as the retrieval pipeline does; the model lists the drivers and teams the request names (`chat-pro`, JSON) |
| `resolve` | code | The race in the lake, the names in its entry list; anything ambiguous or unknown goes to `clarify` |
| `clarify` | ⏸ person | One of the options offered: the latest races for "le dernier GP", the seasons of a Grand Prix with no year, the drivers and teams for an unknown name |
| `plan` | code + model | Code builds the catalog: classification, neutralizations, penalties, and for each driver followed, their stops, their tyre wear and their first pit cycle against the cars that finished next to them (the podium for a race debrief); the model keeps what fits the request, among the catalog's ids only |
| `approve_plan` | ⏸ person | Ticks or unticks analyses |
| `run_tools` | code | The tools of LAB-144 and `penalties`; a tool that fails gives no number, and its point says the data is unavailable |
| `detect_events` | code | Safety cars, VSCs, red flags, and the penalties of the drivers followed: one rule question each kind, 4 at most |
| `retrieve_rules` | pipeline | The retrieval pipeline (ADR-024) answers each question, with its sources, inside the agent's trace |
| `draft` | model | The points, in French, each citing the analyses its numbers come from and the rule sources it uses |
| `verify` | code | Each number in a cited analysis or source, each source retrieved, no number written in words; back to `draft` with the problems, then marked unverified |
| `review` | ⏸ person | Each point approved, corrected (with the text) or rejected, with a reason: `wrong_number`, `wrong_source`, `off_topic`, `wording`, `other` |
| `apply`, `publish` | code | The decisions applied, the debrief rendered in Markdown and stored (`published`), with the decisions |

A request over its limits stops and says which: `AGENT_MAX_STEPS` (40), `AGENT_MAX_LLM_CALLS` (80, the pipeline's included), `AGENT_MAX_TOKENS` (300,000), `AGENT_DRAFTS` (3), `AGENT_MAX_EVENTS` (4), `AGENT_MAX_ANALYSES` (16). The models are `AGENT_PARSE_MODEL`, `AGENT_PLAN_MODEL` and `AGENT_DRAFT_MODEL`, all `chat-pro`: `chat-medium` does not choose tools in a structured answer (LAB-150).

## A question on a chosen race (LAB-203)

From a Grand Prix's page, the analyst asks a precise question, such as "Pourquoi Hamilton est-il parti en pneus tendres ?". The race goes with it: `Agent.start(request, thread_id=..., given={"season": 2024, "round": 18, "question": True})`. `given` holds subject fields the person chose rather than wrote, laid over what `parse` reads, so `resolve` loads that round and its entry list and never asks which race. With `question`:

- the catalog gains `strategies` (`race_strategies`: every driver's starting compound, stints and stop laps, and how many started on each compound, overall and in the top 10) and `weather` (`race_weather`: temperatures at the start and their range, rain). Both are the agent's own tools, like `penalties`, so the baseline's catalog and its evaluation are unchanged;
- the draft answers first, gives the counts the choice is compared with, the driver's grid and finish, then a last point, without numbers, on what the data cannot say (a team's internal reasons), never guessed;
- the plan, the checks of `verify` and the review are the same.

The API takes `season`, `round` and `question` beside `request` (`POST /debriefs`). The front titles such a debrief by its question. Acceptance on Singapore 2024 in `tests/integration/test_agent_acceptance.py`.

Limit: `verify` checks that each number appears in a cited analysis, not that it is not derived from them. In "comme 1 autre pilote sur 20", the 1 is 2 minus Hamilton, and it passes because a 1 appears elsewhere in the output. The review is still what catches it.

## In code

- `core.agent`: the graph (`Agent`, `Theme`, `check_point`), the state (`AgentState` and its models), the PostgreSQL checkpointer and the `published` table (`core.agent.store`). No F1 vocabulary (ADR-011).
- `f1.agent`: the theme (`F1Theme`), `debrief_agent()`, the CLI. Its model calls name `user: f1-agent` at the gateway, the pipeline's `f1-rag`.
- `Agent.start(request, thread_id=...)` runs until the first stop; `Agent.resume(thread_id, answer)` goes on; `Agent.get(thread_id)` reads a request, after a restart too. A `Run` has the state and what it waits for (`waiting.kind`: `clarification`, `plan` or `review`, and its payload). The front of LAB-152 drives the same three methods.

## Measured on 2026-10-15

| Request | Steps | Model calls | Tokens | Time | Points |
| -- | -- | -- | -- | -- | -- |
| Monza 2025 for Ferrari | 12 | 3 | 5,700 | 5 s | 5, all verified at the first draft |
| São Paulo 2024 for Verstappen (VSC, safety car, red flag) | 12 | 17 | 28,000 | 14 s | 4, all verified; two rule questions answered, the red flag one abstained |

Time is the agent's, the person's waits not counted. Drafts vary from a run to the next: another run of Monza needed three drafts and left three of five points unverified.

## Limits

- **The checks see numbers, not meaning.** A true number told misleadingly passes: "Verstappen est resté derrière Ocon" during a pit cycle, true at the time, while he won the race. The review is there for it, and LAB-154 measures how often the analyst corrects or rejects.
- **The catalog is closed.** An analysis it does not hold (the gap to the car ahead lap by lap, the second pit cycle) is code to add in `F1Theme.candidates`.
- **Rules are asked by kind of event**, not by incident: one question for all the safety cars of a race.
