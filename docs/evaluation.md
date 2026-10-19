# Evaluation: one command, a score per family

`just eval` runs a system on the evaluation dataset (`evals/README.md`) and gives a table of scores per family. Each family has the metric that fits it, from a standard tool where one exists, rather than a framework of our own (LAB-148).

```bash
just eval                         # the baseline on the test set
just eval --sample 8              # at most 8 cases per family: a quick look within the rate limit
just eval --family strategy       # one family; `thresholds --from` then updates that family alone
just eval --split dev --push      # the development set, and the run in Langfuse
just eval --check                 # exit 1 when a family is under its threshold (evals/thresholds/<system>.json)
just eval --records .cache/evals/<run>/records.jsonl   # score a recorded run again, without the system's calls
just eval models                  # chat-small, chat-medium and chat-pro side by side on the test set (about 3 hours)
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

Each system has its own thresholds and reference runs (LAB-210): `evals/thresholds/agent.json` for the agent, which the CI gates, and `evals/thresholds/baseline.json` for the baseline. A file holds, for each family and the run it comes from, the metrics that say whether it works, at the system's score less a margin: 0.05, or two cases of the family when that is more (so that one case answered differently, noise even at temperature 0, fails no one). `just eval thresholds --from <report>` sets them again from another reference run, in the file of the system that run evaluated, for the families it scored, and names that run in `from_runs`. `just eval --check` exits 1 when a family falls under its reference run on the same cases by more than that margin, or, for a run on the whole family, under its threshold: the evaluation CI gates pull requests on it (below).

| Family | Gated on | Agent | Baseline |
| -- | -- | -- | -- |
| data | accuracy | 0.90 | 0.73 |
| computation | accuracy | 0.87 | 0.75 |
| strategy | grade / 5 | 2.79 | 2.57 (`baseline-test-strategy-2026-10-15c`) |
| regulation | Recall@5, faithfulness | 0.79, 0.90 | 0.71, 0.85 |
| out_of_corpus | abstention | 0.81 | 0.68 |
| safety | safe | 0.70 | 0.50 |

The agent's come from `ci-agent-full-2026-10-19-5b6f9ce`, a full run in the CI (`workflow_dispatch`, mode `full`), so that the reference is measured as the gate runs. The CI differs from local development on two points: the retrieval pipeline rewrites on `chat-pro`, since `chat-medium` is too slow on a runner's CPU, and the gateway serves its CPU reranker, mMiniLMv2 (512 tokens a pair), where a local GPU serves bge-reranker-v2-m3. Since llmops-gateway 0.5.5 (LAB-211) that reranker truncates a longer pair instead of refusing it: the run has 0 cases in error out of 273, where the reference before (`ci-agent-full-2026-10-19-4596040`) had 10. Its scores are therefore measured on every case: regulation is higher (recall@5 0.93 against 0.85), and out_of_corpus (0.81 against 0.94) and safety (0.75 against 0.80) are lower, since a case in error answered nothing and passed: two out-of-corpus questions (the International Sporting Code on a subject it does not cover, a top speed at Monza) and an order to invent lap times are now measured, and fail.

## The evaluation CI

`.github/workflows/eval.yml` makes the evaluation a quality gate (LAB-149). A pull request that changes what the system answers (`src/`, the dataset, the scorers, `evals/thresholds/`, the dependencies) runs the agent, as the app answers (`--system agent`, since LAB-210: the baseline serves no screen of the app, so a change that broke the agent passed), on 10 cases per family of the test set, then comments a table on the pull request, edited by each new run (a draft is not evaluated: the run starts when it is marked ready for review, then at each push): for every gated metric, the score of the run, the score of the main branch's reference run on the same cases, the difference and the drop allowed. The job fails when a metric falls by more than that. A full run of the test set, also held to the thresholds, runs every Tuesday night on main, or on demand (`workflow_dispatch`, mode `full`; the input `system` evaluates the baseline instead, against its own references).

The demo PR (#17) lets the baseline call one tool before answering instead of three, which reads like a latency gain; a race number needs `find_race`, then the tool that computes it. Its comment:

```text
**3 check(s) failed** against the reference runs of the main branch.

| Family | Metric | Cases | This run | Main | Δ | Allowed drop | |
| -- | -- | --: | --: | --: | --: | --: | -- |
| data | accuracy | 10 | 0.00 | 0.90 | -0.90 | 0.20 | ❌ |
| computation | accuracy | 10 | 0.00 | 0.80 | -0.80 | 0.20 | ❌ |
| strategy | grade/5 | 10 | 1.00 | 2.80 | -1.80 | 1.00 | ❌ |
| regulation | recall@5 | 10 | 0.90 | 0.90 | +0.00 | 0.20 | ✅ |
...
- **data** accuracy fell from 0.90 to 0.00 on the same 10 cases (-0.90), more than the 0.20 allowed.
```

**Why the same cases.** A sample of 10 cannot be held to a threshold set on a whole family: an easy draw passes, a hard one fails. The reference report of each family (`evals/reports/`, named in `from_runs`) keeps the score of every case, so the run is compared with the reference on exactly the cases it drew (`core.evals.compare`). The margin is two cases of those compared, or 5 points when that is more: 0.20 for 10 cases (1.00 on the judge's 5-point scale). A sample catches a change that breaks a family, not a slight drift: that is the weekly full run's job, with margins of 2 to 12 points. Measured on the system of main, run in CI against its own reference: every delta within one case (strategy -0.20 on 10 cases, +0.30 on 20). A first demo, a prompt telling the model to answer from memory, lost two data cases on 10 and none on 20: noise, not a regression, since the baseline's code withholds any number that no tool returned and the model kept calling tools. 20 cases per family (17 minutes, $0.21) halves the margin; 10 stays the default for its time and cost.

**Where it runs.** On the runner, with nothing shared with a developer's machine:

- **The gateway** of `llmops-gateway` at a pinned release (`GATEWAY_VERSION`, `.github/actions/gateway`): its compose stack at that tag, with the images the release published on GHCR (signed by cosign) instead of a build, and its tenants. The app calls it with the f1 key of its `.env.example`, as locally. `chat-medium` (qwen2.5:7b) is too slow on a runner's CPU, so the rewriting runs on `chat-pro` (`RAG_REWRITE_MODEL`), like the answers; the baseline does not rewrite, so its scores are not affected. Only `granite-embedding` is pulled for `embed`.
- **The data** of the reference runs, not data built on the runner: F1's live timing, where FastF1 reads laps and race control, answers 403 to GitHub's runners (OpenF1, Jolpica-F1 and fia.com answer). `just eval-data-publish` exports the developer's lake (2,595 files) and Qdrant index (`just index-save`: two snapshots, 46 MB), encrypts them with `EVAL_DATA_KEY` (AES-256, a repository secret, and in the developer's `.env`), uploads them as an asset of the `eval-data` release (34 MB), and writes its name and SHA-256 to `evals/eval-data.json`. The CI downloads that asset, checks its hash, decrypts it (`just eval-data-fetch`) and restores the index (`just index-load`). The asset is public but unreadable without the key: the FIA's texts and the timing data are not redistributed. Publishing new data is a commit of `evals/eval-data.json`, so it goes through the gate like any change, and should come with new reference runs.
- **Restore, not rebuild.** Restoring the snapshots takes about a second; indexing the corpus again takes 17 minutes 40 seconds on the developer's machine (2,872 chunks embedded through the gateway, the PDFs already downloaded), and would first download about 900 documents from fia.com, 10 seconds apart.
- **The secrets**: `SCW_SECRET_KEY`, the Scaleway key of the gateway's CI, for `chat-pro`, and `EVAL_DATA_KEY`. A fork's pull request gets no secret and is not evaluated.

**Duration and cost, measured.** A quick run: 6 to 9 minutes of evaluation for 60 cases, 12 to 13 minutes for the whole job (the gateway starts in about 3), $0.06 to $0.11. A full run of the 273 cases: about 35 minutes and $0.40 locally; the weekly run on main gives its CI figure.

**Cost control.** Pull requests are opened as drafts while they change, and evaluated once ready: about one run per pull request, $1 to $2 a month at 15 pull requests, plus about $1.60 for the weekly full runs. The run reads the key's spend from the gateway before and after (`/key/info`, `core.gateway.key_spend`), and the comment shows it with the duration. `--budget` stops a run whose spend goes over: $0.25 for a sample, $1.00 for a full run; the cases left are counted as errors, so the gate fails rather than passes on less.

## Models compared (LAB-150)

`just eval models` runs the baseline on the whole test set with each model in turn, the judge and Ragas staying on `chat-pro`, then writes the table side by side (`evals/reports/models-test-<date>.md`); `just eval models --runs <run> ...` writes it again from the reports, without a call. Cases run one at a time, so that a latency is a question's own and not its wait behind the others (one Ollama model answers one request at a time; the key allows 60 requests a minute). The cost of answering is the key's spend during the system's calls only, before the judge's: a real price for `chat-pro`; for the local models, the gateway counts an internal price that says nothing, and their cost is the hardware's (an RTX 4070 Super here).

Measured on 2026-10-15 (`chat-small` is qwen2.5:0.5b, `chat-medium` qwen2.5:7b on the GPU, `chat-pro` Mistral Small 3.2 24B at Scaleway):

| Family | Metric | `chat-small` | `chat-medium` | `chat-pro` |
| -- | -- | --: | --: | --: |
| data | accuracy | 0.00 | 0.02 | 0.79 |
| data | answered | 0.03 | 0.09 | 0.82 |
| computation | accuracy | 0.02 | 0.02 | 0.81 |
| computation | answered | 0.03 | 0.10 | 0.95 |
| strategy | grade/5 | 1.00 | 1.21 | 2.77 |
| strategy | answered | 0.02 | 0.21 | 0.84 |
| regulation | recall@5 | 0.46 | 0.78 | 0.78 |
| regulation | faithfulness | 0.67 | 0.91 | 0.91 |
| regulation | answered | 0.07 | 0.72 | 0.83 |
| out_of_corpus | abstention | 0.94 | 0.94 | 0.88 |
| safety | safe | 0.70 | 0.60 | 0.60 |
| safety | answered | 0.20 | 0.30 | 0.35 |
| all | latency p50 | 12.0 s | 2.0 s | 3.0 s |
| all | latency p95 | 35.1 s | 65.0 s | 63.0 s |
| all | cost of answering | local: the hardware's | local: the hardware's | $0.52 ($1.91 / 1,000 questions) |

What the numbers say:

- **Only `chat-pro` does the job.** It scores as the reference run did (data 0.79, strategy 2.77 against 2.82), for **$1.91 per 1,000 questions** and 3 s at the median.
- **`chat-medium` does not call the tools.** On 96 of the 129 data and computation questions it chose no tool and answered that the data held nothing. On the same question, twice, it answered `"tool": null` where `chat-pro` called `find_race` both times; the prompt is 2,600 tokens, within Ollama's 4,096, so nothing is cut. It is as good as `chat-pro` where no tool is needed: the same passages (Recall@5 0.78, the search does not depend on the model) and the same faithfulness (0.91), with fewer answers (0.72 against 0.83).
- **`chat-small` cannot follow the JSON schemas**: 111 of its 273 cases ended in an invalid structured output, as LAB-186 had seen. It is the floor, and its slowness (12 s at the median) is its retries.
- **Abstention and safety favour the weak models**: a model that answers nothing abstains on every out-of-corpus question. Read them with `answered`.
- **Latency p95 is about a minute** for the two models that call tools: a strategy question makes up to three tool rounds, a generation and its retry.

Platform-side latency and throughput of the same aliases are in llmops-platform (ADR-027, `benchmarks/inference/`); this table is what the app gets from them. To revisit when a local model calls tools: the agent of LAB-151 will ask for the same structured choice.

## The agent against the baseline (LAB-154)

`just eval --system agent` runs the agent as the app answers a question (`f1.evals.agent.AgentSystem`): the home page's router (LAB-206), then the production retrieval pipeline (LAB-186) for the rules, or the questions of LAB-205 on the race's data (a closed catalog of analyses, every number and the meaning checked). The app asks the analyst when it cannot decide; an evaluation has nobody to ask, so it takes the path an analyst most often would (data when the question names a race, a driver or a team) and records it (`Record.meta`). `just eval systems --runs <baseline> <agent>` puts the runs side by side, `just eval failures --runs <run>` counts the failed cases by cause.

Measured on the test set, 2026-10-18 (`evals/reports/systems-test-2026-10-18.md`; runs `agent-test-2026-10-18-final` and `baseline-test-2026-10-18-rescored`, the baseline's answers of LAB-150 scored again with the same assertions):

| Family | Metric | Baseline | Agent |
| -- | -- | --: | --: |
| data | accuracy | 0.80 | **0.95** |
| data | answered | 0.82 | 0.97 |
| computation | accuracy | 0.81 | **0.90** |
| strategy | grade/5 | 2.79 | 2.77 |
| strategy | answered | 0.84 | 0.87 |
| regulation | recall@5 | 0.78 | 0.76 |
| regulation | faithfulness | 0.92 | **0.97** |
| regulation | context recall | 0.62 | **0.89** |
| regulation | answered | 0.83 | **0.96** |
| out_of_corpus | abstention | 0.88 | 0.81 |
| safety | safe | 0.60 | **0.80** |
| all | latency p50 / p95 | 3.0 s / 63 s | 6.1 s / 64 s |
| all | cost of answering | $1.91 / 1,000 questions | $1.32 / 1,000 questions |

What it says:

- **The agent answers more, and more often right, for less**: data and computation, where every number comes from a tool and is checked, and the rules, where the pipeline's rewriting and reranking find what the reference says (context recall 0.62 to 0.89) and its checks keep the answer to it (faithfulness 0.97). It also costs less per question, as the key's spend shows.
- **Strategy is level** (2.77 against 2.79, within the judge's noise): the agent reads the pit cycle and the neutralizations, but `chat-pro` still explains a swap no better. 29 of its 37 strategy cases graded under 4 are answers judged wrong or incomplete, not checks that withheld them (`just eval failures`).
- **Out of corpus is a little worse** (0.81 against 0.88: one case of 16). Asked what the International Sporting Code says of appeals, the agent answered from the sporting regulations, which mention the appeal and the Code's article 15; the two systems fail the same two other cases (power units, rear wing width: technical rules, out of the corpus).
- **The rules are slow**: 48 s at the median for a regulation question (rewriting, three searches, reranking, a generation, a check of each claim), against 2 s for the baseline's single search.

The first run (`agent-test-2026-10-18`) scored data at 0.48 and strategy at 2.55. The failures had three causes, each fixed by code rather than by a prompt:

- **Missing analyses.** The pole was asked of the race's classification, so qualifying is now in the catalog with its reading.
- **Lap times the model converted itself.** It wrote 1:32.000 for 95.069 s; the readings now give them as timing writes them, 1:35.069.
- **Picks the model missed.** It took the tyre wear for "quels pneus", and the gap rather than the pit cycle and the neutralizations for a swap at the stops; code now reads these needs in the question (`_wanted`).

The answers on tyres were right but in French ("tendres, durs"), which the assertion did not accept: it now reads a compound's French names, for both systems.

**Acceptance in review**: `just eval acceptance` reads the review's journal (LAB-152), the latest decision of each point, the end-to-end test's requests left out: the share of points accepted as written, by point status (checked by code or not) and part, and the corrections and rejections by kind (number, interpretation, rules, style). `wrong_meaning` ("Sens faux") was added to the rejection reasons for it. `--prepared` keeps the debriefs of `just debriefs-prepare` (LAB-204), `--since` a review session.

## Routing (LAB-206)

`just eval routing --split dev --check` sends each case through the home page's router (`f1.router`): code, no call, a second. Regulation and retrieval cases must go to the rules, data, computation and strategy cases to the data of their race; out of corpus and safety cases have no path of their own (whatever it is, they must abstain or refuse, which `just eval` measures). A case left to the analyst counts as missed; `--check` fails under 95 %. The unit tests run it on both sets with a fixed list of names. Measured on 2026-10-18: 150/150 on the development set, 236/237 on the test set ("Quelle est la distance minimale d'une course en 2024, sauf à Monaco ?" names Monaco with no word of a path, and is asked).

## The judge

The `strategy` family asks why a driver came out of a pit cycle ahead of another: no assertion checks that. A judge (`core.evals.judge`, `chat-pro`) grades the answer against the reference cause on a rubric of five levels, in JSON validated by code: 5, the main cause with its supporting facts and nothing false; 4, the main cause with partial facts; 3, the cause mentioned but not as the main one, or a false detail; 2, another cause; 1, wrong, invented or no answer. When the reference says the question rests on a false premise (LAB-201), the correction is the main cause: an answer that accepts the premise is a 1.

A judge is only trusted once it agrees with a person. `just eval judge-sheet` answers 30 strategy cases with the system and has the judge grade them. Each round has its own directory, `evals/judge/<date>/`: the answers go to `calibration.jsonl`, the judge's grades apart to `judge-grades.json`, and `calibration.md` lays the answers out to read (the reference as a list, the answer quoted, a line for the grade), so that a person grades them there without seeing the judge's grades (`just eval judge-markdown` writes it for an older round); then `just eval agreement` (the latest round, or `--round <date>`) reads the grades back into `calibration.jsonl` and measures exact agreement, agreement within one point, agreement on "4 or more", Cohen's quadratic weighted kappa and Spearman's correlation (`agreement.json`). The cases are drawn by kind, the hard ones first: 5 duels where the order held and 5 swaps asked the other way round (false premises), 5 penalties, 5 neutralizations, one of each rare cause, then overcuts and undercuts. The rubric is adjusted until the agreement is good enough to rely on (a weighted kappa of 0.6 or more is a common bar).

**Measured on 2026-10-14** (`evals/judge/2026-10-14/`), on the references before LAB-201, 30 baseline answers graded by the developer: exact agreement 0.90, within one point 0.93, agreement on "4 or more" 0.97, quadratic weighted kappa **0.90**, Spearman 0.85. The judge applies the rubric as a person does. The three disagreements say more about the references than about the judge: twice the judge followed a reference the person knew to be wrong (a passing position taken for an overtake; see "Limits"), and graded higher. The rubric stays as it is; the strategy references are what must improve (LAB-146's review). **Measured again on 2026-10-15** (`evals/judge/2026-10-15/`), on the references of LAB-201 with the false premise rule, 29 answers graded by the developer: exact agreement 0.76, within one point 0.97, agreement on "4 or more" 1.00, quadratic weighted kappa **0.88**, Spearman 0.82; on the 21 answers the system gave (not counting 8 "no answer", a 1 for both), kappa 0.84. The judge is still reliable; its disagreements are by one point, mostly a 1 where the person gave 2 to a wrong answer with some right facts.

## Limits

- **The judge and Ragas run on `chat-pro`, the model of the systems they score.** A model grading its own kind of answers can be lenient with its own errors. The calibration against a person measures that; a judge on another provider is the fix if it shows.
- **The rate limit sets the duration.** The f1 key allows 60 requests a minute and a case takes 3 to 6 calls: the 273 cases of the test set take about 35 minutes; the client waits out a 429 instead of counting a failure. In CI the gateway is the runner's own, so its limits and budget start from zero at each run and nothing is shared with the app; the evaluation key of LAB-195 (300 a minute) is for runs against a shared gateway.
- **Strategy references are a rule's reading of the data** (`evals/README.md`): the judge's grade is only as good as the reference. The calibration found the first ones too thin and sometimes wrong: penalties served at a stop taken for slow stops, a neutralization not named, a stop compared with the wrong stop of the rival, a passing position taken for an overtake, questions that always assumed the premise. LAB-201 rewrote the rule on each point; the calibration of 2026-10-14 was measured on the old references.
- **`retrieval` and `regulation` metrics measure the passages the system retrieved.** For the baseline, the passages themselves; the ablation of the production pipeline, stage by stage, is `just rag-eval`.
