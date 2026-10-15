# ADR-012: Evaluation with promptfoo, Ragas, a calibrated judge and Langfuse, not one framework

- **Status:** Accepted
- **Date:** 2026-10-15

## Context

The app has to be tested like code: a change of prompt, model or configuration that makes answers worse must not be merged (LAB-149). The test set of LAB-146 holds 273 cases of seven families that need different checks:

- **Exact answers** (`data`, `computation`, 129 cases): a lap time, a gap, a pit loss, in French, with a decimal comma, within a tolerance.
- **Answers from sources** (`regulation`, `retrieval`, 46 + 30 cases): are the right articles retrieved, and does the answer say only what they say?
- **Refusals** (`out_of_corpus`, `safety`, 36 cases): the system must decline or abstain.
- **Explanations** (`strategy`, 62 cases): why a driver came out of a pit cycle ahead of another. No assertion checks that.

Two constraints shape the choice. The system's calls are what costs (about 40 cents and 35 minutes for the test set, at 60 requests a minute): every scorer must run on recorded answers, so that a scorer can change without paying the system again. And the platform already runs Langfuse behind the gateway (llmops-gateway), with a project per team, where every model call of the app is traced.

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. A standard tool per kind of check, on records of one run: promptfoo for assertions, Ragas for answers from sources, an LLM judge of our own for explanations, Langfuse for datasets and runs | Each family gets the metric that fits it, from a tool known for it; scorers rerun without the system; runs land next to the traces the platform already keeps | Three tools and a harness to tie them (`core.evals.harness`, 370 lines); Ragas needs its own environment |
| B. One framework for everything (DeepEval) | One API, pytest-style, many metrics | Its LLM metrics overlap Ragas's; it has no metric for "why did this happen in a race" either, so the judge is written anyway; its hosted platform duplicates Langfuse |
| C. A framework of our own | Exactly what we need | Number parsing, retrieval metrics and faithfulness rewritten and untested by anyone else; nothing to show a reader that they can reuse |
| D. A, plus MLflow to keep the runs | A run history with charts | A second store of runs beside Langfuse, which already links each case of a run to its trace and its scores |

## Decision

We choose **A**:

1. **The system runs once per case**, and each case's record (answer, abstention, passages and tool results read, latency, trace id) is appended as it comes (`--resume` goes on after an interruption). Scorers read the records.
2. **promptfoo** (`npx promptfoo@0.123.1`, pinned) checks `data`, `computation`, `safety` and `out_of_corpus` with a provider that returns the recorded answer instead of calling a model, and checks in `evals/promptfoo/assertions.js`: numbers within their tolerance, French decimal comma and lap times accepted, refusals.
3. **Ragas** (0.4.3) scores the faithfulness of `regulation` answers to what the system read, and the recall of the reference in it. It runs in its own environment (`evals/ragas/`), because it needs `openai` < 3 and the app runs on 3.
4. **Retrieval metrics are code** (Recall@5, MRR@10, nDCG@5 on distinct sources, `core.retrieval.evaluation`): a few lines, no tool needed.
5. **An LLM judge of our own** grades `strategy` answers against a reference on a five-level rubric, in JSON validated by Pydantic (`core.evals.judge`). It is trusted because it was calibrated against a person: 30 answers graded by both, quadratic weighted kappa 0.90, then 0.88 after LAB-201 rewrote the references (`docs/evaluation.md`).
6. **Langfuse** holds the dataset (`f1-dev`, `f1-test`) and each run, every case linked to its trace with its scores. **No MLflow**: the reports in `evals/reports/` are the history the gate compares against, and Langfuse is where a run is explored.

## Consequences

- A scorer, a rubric or an assertion can change and be rerun on yesterday's records in a minute (`just eval --records`), without the 35 minutes and 40 cents of the system.
- The gate of LAB-149 compares a pull request with the main branch case by case, because every report keeps every case's scores.
- The judge and Ragas run on `chat-pro`, the model of the system they score: a model can be lenient with its own kind of errors. The calibration measures it; a judge on another provider is the fix if a new calibration shows it.
- Three tools mean three upgrades to follow and two Python environments: Ragas and Langfuse through their lock files, promptfoo through the version pinned in `core.evals.harness` (`PROMPTFOO`), which Renovate does not see.
- To revisit: if the agent of LAB-151 needs checks that none of these tools has (a debrief's numbers against the tools' values, its sources against the passages), they go in the agent's `verify` node and in the harness, not in a new framework; MLflow comes back if runs must be compared over months on charts Langfuse does not draw.
