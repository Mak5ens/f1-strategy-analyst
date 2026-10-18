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
| `run_tools` | code | The tools of LAB-144 and `penalties`; a tool that fails gives no number, and its point says the data is unavailable. Each output gets its `lecture`, what it means in French, written by code (`f1.agent.readings`) |
| `detect_events` | code | Safety cars, VSCs, red flags, and the penalties of the drivers followed: one rule question each kind, 4 at most |
| `retrieve_rules` | pipeline | The retrieval pipeline (ADR-024) answers each question, with its sources, inside the agent's trace |
| `draft` | model | In French: a summary, 3 to 5 titled moments and a takeaway without a number (code then orders the moments by the first lap each names, kept in `Point.when` for the timeline), each citing the analyses its numbers and its meaning come from, and the rule sources it uses |
| `verify` | code + model | Each number in a cited analysis or source, each source retrieved, no number written in words nor in a title or the takeaway; then the meaning (`faithful`): who was ahead checked by code, the rest by a model against the readings. Back to `draft` with the problems, then marked unverified |
| `review` | ⏸ person | Each point approved, corrected (with the text) or rejected, with a reason: `wrong_number`, `wrong_source`, `off_topic`, `wording`, `other` |
| `apply`, `publish` | code | The decisions applied, the debrief rendered in Markdown and stored (`published`), with the decisions |

A request over its limits stops and says which: `AGENT_MAX_STEPS` (40), `AGENT_MAX_LLM_CALLS` (80, the pipeline's included), `AGENT_MAX_TOKENS` (300,000), `AGENT_DRAFTS` (3), `AGENT_MAX_EVENTS` (4), `AGENT_MAX_ANALYSES` (16). The models are `AGENT_PARSE_MODEL`, `AGENT_PLAN_MODEL`, `AGENT_DRAFT_MODEL` and `AGENT_VERIFY_MODEL`, all `chat-pro`: `chat-medium` does not choose tools in a structured answer (LAB-150).

## A debrief that explains (LAB-207)

The first debriefs lined up right numbers and explained nothing ("Leclerc s'arrête au tour 33, perd 24,8 s, et passe des pneus medium aux durs"). Asked for prose, the model read a pit cycle backwards ("Leclerc perd du terrain sur Piastri par l'undercut", when the undercut gained 3 s, not enough to pass), compared a tyre wear with a driver nobody measured, and gave causes no analysis showed. Every number was right: the meaning was the model's, and nothing checked it. Three changes:

- **Code writes the meaning.** Each analysis carries its `lecture` (`f1.agent.readings`): who stayed ahead at a pit cycle, whose undercut or overcut it was, what it gained or cost, the gap before and after, the laps between the stops; the places gained from the grid to the finish; a tyre wear too loosely measured to say anything (fit under 0.3) is said so. The model tells and links these readings instead of deducing them.
- **A structure and rules for prose**: a summary (start, finish, what decided it), 3 to 5 moments with a title without a number whose subject is the driver who acts, a takeaway without a number. Places gained only from the classification, comparisons only on an analysis that measures both drivers, no cause nor intention no analysis shows. A style example on imaginary drivers, with no number in it: the model copied the example's numbers and claims when it had some.
- **The meaning is checked** after the numbers (`Theme.faithful`, also run on the questions of LAB-205). Who was ahead of whom is data: code reads "A reste devant B", "A finit derrière B", "A passe B" and compares them with the pit cycles and the classification (`order_problems`). A model given the right reading still judged "Leclerc reste devant Piastri" as shown, quoting the reading that said the opposite. The rest goes to a model, claim by claim: it quotes the reading it judges against, then says shown, contradicted or not shown. A problem sends the draft back, as a number does.

Measured on Monza 2025 for Ferrari, 2026-10-18: the meaning check caught the three wrong points written on purpose (a cycle backwards, a wear compared with a driver not measured, a cause not shown) and passed the five right ones. A debrief takes 13 to 23 model calls and 50,000 to 65,000 tokens, against 3 and 5,700 before: each draft is read again point by point. With `chat-pro` (Mistral Small 24B) the moments come out right and readable, with constructions that still repeat; a summary may need the review, as on that run (a number in words, then a claim the meaning check had not read yet).

## A question on a chosen race (LAB-203)

From a Grand Prix's page, the analyst asks a precise question, such as "Pourquoi Hamilton est-il parti en pneus tendres ?". The race goes with it: `Agent.start(request, thread_id=..., given={"season": 2024, "round": 18, "question": True})`. `given` holds subject fields the person chose rather than wrote, laid over what `parse` reads, so `resolve` loads that round and its entry list and never asks which race. With `question`:

- the catalog gains `strategies` (`race_strategies`: every driver's starting compound, stints and stop laps, and how many started on each compound, overall and in the top 10) and `weather` (`race_weather`: temperatures at the start and their range, rain). Both are the agent's own tools, like `penalties`, so the baseline's catalog and its evaluation are unchanged;
- the draft answers first, gives the counts the choice is compared with, the driver's grid and finish, then a last point, without numbers, on what the data cannot say (a team's internal reasons), never guessed;
- the plan, the checks of `verify` and the review are the same.

The API takes `season`, `round` and `question` beside `request` (`POST /debriefs`). The front titles such a debrief by its question. Acceptance on Singapore 2024 in `tests/integration/test_agent_acceptance.py`.

Limit: `verify` checks that each number appears in a cited analysis, not that it is not derived from them. In "comme 1 autre pilote sur 20", the 1 is 2 minus Hamilton, and it passes because a 1 appears elsewhere in the output. The review is still what catches it.

## Questions on a published debrief (LAB-205)

Under a published debrief, the analyst asks to detail a point: "Détaille le cycle d'arrêts de Leclerc face à Russell", "Et sous la voiture de sécurité ?". The answer is direct, with no person in between, so code bounds it (`core.agent.chat.Chat`, filled by `F1Theme.scope`, `pick` and `reply`):

| Step | Who | What |
| -- | -- | -- |
| `scope` | code | A question naming another Grand Prix or season is refused before any model call, saying where to ask it: that race's page, or a free question from the home page |
| `pick` | model | Among the debrief's own catalog only, the analyses needed beyond those already run (3 at most), and a question on the rules if any; code adds the season to it, as the retrieval filters on it |
| run, rule | code | The tools; the retrieval pipeline for the rule question |
| `reply` | model | 1 to 4 short points, the answer first, citing their analyses and sources; the questions answered before are context, not a source |
| check | code | `check_point` and `F1Theme.check`, as for a debrief; a reply that fails is written once more with its problems, then withheld, and says why |

`F1Theme.check` also refuses an article named without its source ("B6.2.4"): an identifier escapes the number check, so it must be cited. Limits per question (`AGENT_CHAT_*`: 12 model calls, 80,000 tokens); calls go to the gateway as `user: f1-agent-chat`. Every question and its reply, whatever its status, is kept in the `questions` table (`RequestStore.save_reply`), shown under the debrief (`GET` and `POST /debriefs/{id}/questions`), the answered ones passed back as history.

## The free question of the home page (LAB-206)

The home page has one field for what does not start from a race: a rule ("Que risque une équipe en cas de libération dangereuse au stand ?"), a number of a race ("Quel écart entre Leclerc et Russell au tour 20 du GP d'Italie 2025 ?"), or a debrief. The analyst never picks a tool: code routes the question (`f1.router.Router`), as the retrieval pipeline reads its filters, without a model to trust, pay for and evaluate.

| The question | Path | What answers |
| -- | -- | -- |
| asks for a debrief ("débrief", "bilan stratégique") | `debrief` | the agent, started by `POST /questions`: the front opens its request (plan, review, publication) |
| names no race, no driver, no team | `rules` | the retrieval pipeline: claims citing their FIA passages, or an abstention |
| names one, with the words of the rules (règlement, autorisé, peut-on, commissaires, a sanction asked "pourquoi") | `rules` | the same; a link to the race's page when it names one |
| names one, with the words of the data (combien, écart, pole, arrêts, "pourquoi" without a sanction) | `data` | the questions of LAB-205 on that race (`Chat`), on a subject built by code |
| both, or neither | none | the analyst chooses the path: nothing is guessed |

The drivers and teams are those of the lake (`GrandPrix.people`), matched in full or by last name. On the `data` path, `F1Theme.free_subject` builds the subject the chat starts from, with no debrief behind it: the race (one season and one Grand Prix the data knows, else the analyst chooses among the races run), the drivers and teams named, the laps cited ("au tour 43", which adds the gap between two drivers named on those laps to the catalog) and the stop ("2es arrêts", for the pit cycle). The pick then has its own prompt: no analysis is run yet. Every question and what came of it is kept (`free_questions` table, `GET /questions`), the latest shown on the home page.

`just eval routing` measures the path taken on each case of the dataset, by family (`docs/evaluation.md`): 150 of 150 on the development set, 236 of 237 on the test set, the one missed left to the analyst rather than sent the wrong way.

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

- **The meaning check is a model's, but for who was ahead.** It catches a cycle read backwards or a cause not shown; it may miss a subtler misreading, and it reads a point only once its numbers hold. The review stays the last check, and LAB-154 measures how often the analyst corrects or rejects.
- **The drafting model limits the prose.** `chat-pro` repeats its constructions from a moment to the next. A larger model is an alias to add to the gateway.
- **The catalog is closed.** An analysis it does not hold is code to add in `F1Theme.candidates`. A question may now ask for the gap between two drivers it names on the laps it cites, and for a pit cycle after the first stop; a debrief still has neither.
- **The routing reads words.** A question in other words than the dataset's may take the other path or be left to the analyst; a question on the data that names neither a race, a driver nor a team goes to the rules, which abstain. A sanction asked "pourquoi" goes to the stewards' decisions, not to the race's penalties.
- **A false abstention of the rules is shown as is.** "Peut-on changer de pneus sous drapeau rouge en 2025 ?" abstains: the passage that answers (article 57.4) gets a rerank score of 0.20, under the threshold of 0.43 (`evals/rag/reports/dev-2026-10-14-lab146.json`).
- **Rules are asked by kind of event**, not by incident: one question for all the safety cars of a race.
