# ADR-025: The debrief agent is a fixed graph whose routing is code, not a free ReAct agent

- **Status:** Accepted
- **Date:** 2026-10-15

## Context

The agent writes a strategy debrief of a Grand Prix for an analyst, who stops it three times: to clarify an ambiguous request, to validate the plan, and to review each point before it is published (plan of 2026-10-10, LAB-151). The demand behind it is to **control what it does at every step**: a debrief quoting a wrong pit loss or an invented rule is worse than none, and the analyst must be able to tell why the agent did each thing.

Facts measured before the choice:

- `chat-medium` (qwen2.5:7b) does not call tools from a structured choice: on 96 of 129 questions with a number it answered `"tool": null` (LAB-150). `chat-pro` (Mistral Small 3.2) does, and matches the reference runs.
- A model writes numbers it computed: in the first debriefs, "Russell, qui a arrêté un tour plus tôt" (it was 6 laps, 27 against 33), and a stop "costing 1,539 seconds" under a red flag (the stoppage, counted by the tool as lost time; the tool now gives none).
- A request waits for a person for minutes or days: it must survive a restart of the service.

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. A fixed LangGraph graph: code routes, a model fills four bounded nodes (parse, choose, rule, draft) with JSON validated by Pydantic, code checks every number | Every path is known and testable without a model; the three stops are LangGraph interrupts with a PostgreSQL checkpointer; one span per node explains each choice | Less flexible: an analysis outside the catalog needs code; more code than a prompt |
| B. A ReAct agent with the tools (LangGraph's prebuilt agent, or the model's tool calling in a loop) | Little code; handles requests nobody planned | Unbounded calls and paths; which tool it calls, and when it stops, depend on the model (`chat-medium` would call none); a stop for a person is wherever the model asks for one |
| C. The baseline (LAB-147) with a longer prompt | Already measured | No plan to validate, no point-by-point review, three tool rounds at most |

## Decision

We choose **A**, the skeleton in `core.agent` (no F1 vocabulary, ADR-011) and the nodes' content in `f1.agent.theme`:

1. **Thirteen nodes, routed by code**: parse, resolve, clarify, plan, approve_plan, run_tools, detect_events, retrieve_rules, draft, verify, review, apply, publish. Each node returns its routing decision (`next`); the edges only read it.
2. **What code decides, never a model**: the season and the Grand Prix (read in the request as the retrieval pipeline reads them), the drivers and teams (matched against the race's entry list), the catalog of analyses (tools and arguments), the events a rule explains (neutralizations and penalties, from the tools), every number (the tools).
3. **What a model does, validated by code**: list the drivers and teams the request names; pick analyses in the closed catalog (an enum built from it: an id outside is dropped); answer each event's rule question (the retrieval pipeline of ADR-024); write the points from the tools' outputs and the rules found.
4. **The three stops are interrupts**, in nodes of their own that only ask and record, so a node run again after a resume asks again and nothing else. An answer outside what was asked (an option not offered, a point without a decision, a correction without its text) is asked again, never guessed.
5. **`verify` is code**: each number of a point must be in the outputs of the analyses it cites, or a rule source it cites (`core.numbers`), each source must be one the retrieval found, and the theme adds its checks (a number written in words: "un tour plus tôt"). A point that fails goes back to `draft` with its problems, three drafts at most, then reaches the analyst marked unverified. An analysis that failed gives no number: its point says the data is unavailable.
6. **Limits per request**, on top of the team's budget at the gateway: 40 steps, 80 model calls (the retrieval pipeline's included, counted by the gateway transport), 300,000 tokens, 4 rule questions, 16 analyses (`AGENT_*`). Over a limit, the request stops and says which.
7. **State and storage**: the state is a Pydantic model saved by LangGraph's PostgreSQL checkpointer after every node; published debriefs are rows of their own (`published`), with the review's decisions.
8. **Tracing**: one Langfuse span per node, input and output, all in one trace for the request, resumes included; the gateway's model calls join it by `session_id`. Every node calling a model runs on `chat-pro` (`AGENT_*_MODEL`).

## Consequences

- A whole debrief costs 3 model calls when no rule is needed (Monza 2025 for Ferrari: 12 steps, about 5,700 tokens, 5 seconds), 17 with three neutralizations (São Paulo 2024 for Verstappen: about 28,000 tokens, 14 seconds).
- The graph is tested without a model (`tests/unit/test_agent.py`: the stops, the catalog, the checks, the drafts again, the limits, a resume by a new agent), and on the stack (`tests/integration/test_agent_acceptance.py`: a restart at each of the three waits, every number backed, an ambiguous request).
- Strict checks leave points unverified: in one run, three of five points after three drafts (a number copied from an analysis the point did not cite, "une place" written in words). The analyst sees them marked, with their problems; the share of points approved without correction is what LAB-154 measures.
- What the checks cannot see: a true number told misleadingly ("resté derrière Ocon" during a pit cycle that Verstappen won later). That is what the review is for.
- An analysis the catalog does not hold is code to write. To revisit if analysts keep rejecting points for a missing analysis (reason `off_topic` or `other` in the review log), or if a local model chooses well enough for `plan` to run on it.
