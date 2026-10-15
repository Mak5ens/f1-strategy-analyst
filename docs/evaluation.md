# Evaluation: one command, a score per family

`just eval` runs a system on the evaluation dataset (`evals/README.md`) and gives a table of scores per family. Each family has the metric that fits it, from a standard tool where one exists, rather than a framework of our own (LAB-148).

```bash
just eval                         # the baseline on the test set
just eval --sample 8              # at most 8 cases per family: a quick look within the rate limit
just eval --family strategy       # one family; `thresholds --from` then updates that family alone
just eval --split dev --push      # the development set, and the run in Langfuse
just eval --check                 # exit 1 when a family is under its threshold (evals/thresholds.json)
just eval --records .cache/evals/<run>/records.jsonl   # score a recorded run again, without the system's calls
just rag-eval --cases evals/datasets/test.jsonl         # retrieval ablation, stage by stage
```

## How a run goes

1. **The system answers each case once** (`core.evals.harness.run_system`), four cases at a time. Each case's record holds the answer (or the abstention), the passages and tool results the model read, the passages retrieved, the tools called, the latency and the Langfuse trace id. A case that raises is recorded as an error, which every check counts as a failure.
2. **Every scorer reads the records**, so a scorer can change without paying the system's calls again:

| Family | Scored by | Metric |
| -- | -- | -- |
| `data`, `computation` | [promptfoo](https://www.promptfoo.dev/) | `accuracy`: the expected value is in the answer (numbers within their tolerance, French decimal comma and lap times accepted, zero said in words) |
| `safety` | promptfoo | `safe`: nothing that must not appear, and a refusal when the case asks for one |
| `out_of_corpus` | promptfoo | `abstention`: the system declined |
| `retrieval`, `regulation` | code | `recall@5`, `mrr@10`, `ndcg@5` on the distinct sources retrieved |
| `regulation` | [Ragas](https://docs.ragas.io/) | `faithfulness` of the answer to what it read; `context_recall` of the reference answer in it |
| `strategy` | LLM judge | `grade/5` on an explicit rubric, and `graded_4+` |

Every family also shows `answered` (share of answers given) and `median_s`.

**The report** goes to `evals/reports/<run>.json`: the scores per family, per case, and the judge's grades with their reasons. With `--push`, each traced case is linked to its item of the Langfuse dataset (`f1-test` or `f1-dev`) under the run's name, and its scores are put on its trace: Langfuse compares runs, per case, per family, per version.

promptfoo and Ragas run apart: promptfoo with `npx` (pinned, `promptfoo@0.123.1`), on a provider that replays the recorded answers (`evals/promptfoo/recorded.py`) and checks written once in `evals/promptfoo/assertions.js`; Ragas in its own environment (`evals/ragas/`, its own lock), since it needs `openai` < 3 and the app `openai` 3.

## The baseline on the test set

`just eval --split test --push` on 2026-10-14, the baseline of LAB-147 (`evals/reports/baseline-test-2026-10-14.json`, dataset run `baseline-test-2026-10-14` in Langfuse):

| Family | Cases | Score | Answered |
| -- | -- | -- | -- |
| data | 66 | accuracy 0.79 | 0.82 |
| computation | 63 | accuracy 0.81 | 0.94 |
| strategy | 37 | grade 2.24 / 5, 24 % graded 4 or more | 0.68 |
| regulation | 46 | Recall@5 0.76, MRR@10 0.68, nDCG@5 0.77; faithfulness 0.91, context recall 0.60 | 0.83 |
| out_of_corpus | 16 | abstention 0.81 | |
| safety | 20 | safe 0.60 | 0.35 |

- The run took 35 minutes for 248 cases, plus the scoring: the f1 key's 60 requests a minute set the pace, so the medians it shows (about 60 s for a case with tools) are mostly waits for the limit, not latency. One case failed: `chat-pro` gave no valid answer JSON in two attempts, counted as a failure.
- **The weak spots of a naive system**, which the pipeline and the agent must close: strategy (it reads the stops but rarely explains the swap), the safety cases (it follows an injected order 40 % of the time), and context recall on rules (the dense search on the French question misses part of what the reference says).
- Faithfulness is high (0.91): when it answers a rule question, it sticks to what it read; what it read is often incomplete.
- **Strategy on the new references** (LAB-201, `just eval --family strategy`): 60 cases.
  - `baseline-test-strategy-2026-10-15`: grade 1.93 / 5. In 6 of the 30 answers of the calibration round, the baseline called the winner's undercut an overcut, or the reverse: `pit_cycle` said `kind` from the side of the `driver` asked about, and the model asked about the loser.
  - `baseline-test-strategy-2026-10-15b`, with `pit_cycle` giving the outcome from the winner's side and a sentence that says it, and the references with the race's context: grade **2.48 / 5**, 37 % graded 4 or more, no undercut and overcut mixed up. Undercuts 3.12, overcuts 4.25, neutral questions 3.38, leading 2.88. It still accepts every false premise (1.00, 19 cases) and still rarely names a penalty or a neutralization (2.00 each): reading the stewards' messages, the track status and the premise is the agent's job.
  - `baseline-test-strategy-2026-10-15c`, once the references gave the duel's history over the race, a duel where the order held had to hold to the next stop or the flag (a pass on track 4 laps later is still a lost place), and the questions named the laps of the stops: 62 cases, grade **2.82 / 5**, 42 % graded 4 or more; false premises 1.57, undercuts 3.56, overcuts 4.50, neutralizations 2.64, penalties 2.00. The laps in the question help the baseline find the right stops; part of the gain is that.
- The test set holds no `retrieval` case (the 30 of LAB-186 are all in the development set): retrieval on the test set is measured on the `regulation` questions.

## Thresholds

`evals/thresholds.json` holds, for each family and the run it comes from, the metrics that say whether it works, at the baseline's score less a margin: 0.05, or two cases of the family when that is more (so that one case answered differently, noise even at temperature 0, fails no one). `just eval thresholds --from <report>` sets them again from another reference run, for the families that run scored, and names that run in `from_runs`. `just eval --check` exits 1 when a family falls under its reference run on the same cases by more than that margin, or, for a run on the whole family, under its threshold: the evaluation CI gates pull requests on it (below).

| Family | Gated on | Threshold |
| -- | -- | -- |
| data | accuracy | 0.73 |
| computation | accuracy | 0.75 |
| strategy | grade / 5 | 2.57 (`baseline-test-strategy-2026-10-15c`) |
| regulation | Recall@5, faithfulness | 0.71, 0.85 |
| out_of_corpus | abstention | 0.68 |
| safety | safe | 0.50 |

## The evaluation CI

`.github/workflows/eval.yml` makes the evaluation a quality gate (LAB-149). A pull request that changes what the system answers (`src/`, the dataset, the scorers, `evals/thresholds.json`, the dependencies) runs the baseline on 10 cases per family of the test set, then comments a table on the pull request, edited by each new run: for every gated metric, the score of the run, the score of the main branch's reference run on the same cases, the difference and the drop allowed. The job fails when a metric falls by more than that. A full run of the test set, also held to the thresholds, runs every Tuesday night on main, or on demand (`workflow_dispatch`, mode `full`).

```text
| Family | Metric | Cases | This run | Main | Δ | Allowed drop | |
| -- | -- | --: | --: | --: | --: | --: | -- |
| strategy | grade/5 | 10 | 1.40 | 2.90 | -1.50 | 1.00 | ❌ |

- **strategy** grade/5 fell from 2.90 to 1.40 on the same 10 cases (-1.50), more than the 1.00 allowed.
```

**Why the same cases.** A sample of 10 cannot be held to a threshold set on a whole family: an easy draw passes, a hard one fails. The reference report of each family (`evals/reports/`, named in `from_runs`) keeps the score of every case, so the run is compared with the reference on exactly the cases it drew (`core.evals.compare`). The margin is two cases of those compared, or 5 points when that is more: 0.20 for 10 cases (1.00 on the judge's 5-point scale). A sample catches a change that breaks a family, not a slight drift: that is the weekly full run's job, with margins of 2 to 12 points.

**Where it runs.** On the runner, with nothing shared with a developer's machine:

- **The gateway** of `llmops-gateway` at a pinned release (`GATEWAY_VERSION`, `.github/actions/gateway`): its compose stack at that tag, with the images the release published on GHCR (signed by cosign) instead of a build, and its tenants. The app calls it with the f1 key of its `.env.example`, as locally. `chat-medium` (qwen2.5:7b) is too slow on a runner's CPU, so the rewriting runs on `chat-pro` (`RAG_REWRITE_MODEL`), like the answers; the baseline does not rewrite, so its scores are not affected. Only `granite-embedding` is pulled for `embed`.
- **The data**, built by `.github/workflows/eval-data.yml` and kept in the Actions cache, never in the repository: the lake (one cache per season, ingested in parallel because FastF1 allows 500 calls an hour) and the Qdrant index as snapshots (`just index-save`, `just index-load`). It runs twice a week (an Actions cache entry unused for 7 days is dropped), on demand, and when the ingestion or the corpus code changes on main. The HTTP caches of FastF1 and fia.com are saved too, even on a failure, so a first build cut by the 6-hour limit goes on where it stopped.
- **The secret**: `SCW_SECRET_KEY`, the Scaleway key of the gateway's CI, for `chat-pro`. A fork's pull request gets no secret and is not evaluated.

**Cost.** The run reads the key's spend from the gateway before and after (`/key/info`, `core.gateway.key_spend`), and the comment shows it with the duration. `--budget` stops a run whose spend goes over: $0.25 for a sample, $1.00 for a full run; the cases left are counted as errors, so the gate fails rather than passes on less.

## The judge

The `strategy` family asks why a driver came out of a pit cycle ahead of another: no assertion checks that. A judge (`core.evals.judge`, `chat-pro`) grades the answer against the reference cause on a rubric of five levels, in JSON validated by code: 5, the main cause with its supporting facts and nothing false; 4, the main cause with partial facts; 3, the cause mentioned but not as the main one, or a false detail; 2, another cause; 1, wrong, invented or no answer. When the reference says the question rests on a false premise (LAB-201), the correction is the main cause: an answer that accepts the premise is a 1.

A judge is only trusted once it agrees with a person. `just eval judge-sheet` answers 30 strategy cases with the system and has the judge grade them. Each round has its own directory, `evals/judge/<date>/`: the answers go to `calibration.jsonl`, the judge's grades apart to `judge-grades.json`, and `calibration.md` lays the answers out to read (the reference as a list, the answer quoted, a line for the grade), so that a person grades them there without seeing the judge's grades (`just eval judge-markdown` writes it for an older round); then `just eval agreement` (the latest round, or `--round <date>`) reads the grades back into `calibration.jsonl` and measures exact agreement, agreement within one point, agreement on "4 or more", Cohen's quadratic weighted kappa and Spearman's correlation (`agreement.json`). The cases are drawn by kind, the hard ones first: 5 duels where the order held and 5 swaps asked the other way round (false premises), 5 penalties, 5 neutralizations, one of each rare cause, then overcuts and undercuts. The rubric is adjusted until the agreement is good enough to rely on (a weighted kappa of 0.6 or more is a common bar).

**Measured on 2026-10-14** (`evals/judge/2026-10-14/`), on the references before LAB-201, 30 baseline answers graded by the developer: exact agreement 0.90, within one point 0.93, agreement on "4 or more" 0.97, quadratic weighted kappa **0.90**, Spearman 0.85. The judge applies the rubric as a person does. The three disagreements say more about the references than about the judge: twice the judge followed a reference the person knew to be wrong (a passing position taken for an overtake; see "Limits"), and graded higher. The rubric stays as it is; the strategy references are what must improve (LAB-146's review). **Measured again on 2026-10-15** (`evals/judge/2026-10-15/`), on the references of LAB-201 with the false premise rule, 29 answers graded by the developer: exact agreement 0.76, within one point 0.97, agreement on "4 or more" 1.00, quadratic weighted kappa **0.88**, Spearman 0.82; on the 21 answers the system gave (not counting 8 "no answer", a 1 for both), kappa 0.84. The judge is still reliable; its disagreements are by one point, mostly a 1 where the person gave 2 to a wrong answer with some right facts.

## Limits

- **The judge and Ragas run on `chat-pro`, the model of the systems they score.** A model grading its own kind of answers can be lenient with its own errors. The calibration against a person measures that; a judge on another provider is the fix if it shows.
- **The rate limit sets the duration.** The f1 key allows 60 requests a minute and a case takes 3 to 6 calls: the 248 cases of the test set take about 25 minutes, over the 15 aimed at. The evaluation key of LAB-195 (300 a minute) brings it under. Until then, `--sample` gives a quick look; the client waits out a 429 instead of counting a failure.
- **Strategy references are a rule's reading of the data** (`evals/README.md`): the judge's grade is only as good as the reference. The calibration found the first ones too thin and sometimes wrong: penalties served at a stop taken for slow stops, a neutralization not named, a stop compared with the wrong stop of the rival, a passing position taken for an overtake, questions that always assumed the premise. LAB-201 rewrote the rule on each point; the calibration of 2026-10-14 was measured on the old references.
- **`retrieval` and `regulation` metrics measure the passages the system retrieved.** For the baseline, the passages themselves; the ablation of the production pipeline, stage by stage, is `just rag-eval`.
