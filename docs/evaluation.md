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
- **Strategy on the new references** (LAB-201, `evals/reports/baseline-test-strategy-2026-10-15.json`, `just eval --family strategy`): 60 cases, grade **1.93 / 5**, 12 % graded 4 or more. The baseline accepts 18 of the 19 false premises (graded 1); on the others it does better on neutral questions (2.50) than on leading ones (2.06), and best on overcuts (3.25, 4 cases). It names a penalty or a neutralization rarely (2.00 each): reading the stewards' messages and the track status is the agent's job.
- The test set holds no `retrieval` case (the 30 of LAB-186 are all in the development set): retrieval on the test set is measured on the `regulation` questions.

## Thresholds

`evals/thresholds.json` holds, for each family and the run it comes from, the metrics that say whether it works, at the baseline's score less a margin: 0.05, or two cases of the family when that is more (so that one case answered differently, noise even at temperature 0, fails no one). `just eval thresholds --from <report>` sets them again from another reference run, for the families that run scored; `just eval --check` exits 1 when a family is under its threshold, which the evaluation CI (LAB-149) gates pull requests on.

| Family | Gated on | Threshold |
| -- | -- | -- |
| data | accuracy | 0.73 |
| computation | accuracy | 0.75 |
| strategy | grade / 5 | 1.68 (from the run on the LAB-201 references) |
| regulation | Recall@5, faithfulness | 0.71, 0.85 |
| out_of_corpus | abstention | 0.68 |
| safety | safe | 0.50 |

## The judge

The `strategy` family asks why a driver came out of a pit cycle ahead of another: no assertion checks that. A judge (`core.evals.judge`, `chat-pro`) grades the answer against the reference cause on a rubric of five levels, in JSON validated by code: 5, the main cause with its supporting facts and nothing false; 4, the main cause with partial facts; 3, the cause mentioned but not as the main one, or a false detail; 2, another cause; 1, wrong, invented or no answer. When the reference says the question rests on a false premise (LAB-201), the correction is the main cause: an answer that accepts the premise is a 1.

A judge is only trusted once it agrees with a person. `just eval judge-sheet` answers 30 strategy cases with the system and has the judge grade them. Each round has its own directory, `evals/judge/<date>/`: the answers go to `calibration.jsonl`, the judge's grades apart to `judge-grades.json`, so that a person sets `human` on each line without seeing them; then `just eval agreement` (the latest round, or `--round <date>`) measures exact agreement, agreement within one point, agreement on "4 or more", Cohen's quadratic weighted kappa and Spearman's correlation (`agreement.json`). The cases are drawn by kind, the hard ones first: 5 duels where the order held and 5 swaps asked the other way round (false premises), 5 penalties, 5 neutralizations, one of each rare cause, then overcuts and undercuts. The rubric is adjusted until the agreement is good enough to rely on (a weighted kappa of 0.6 or more is a common bar).

**Measured on 2026-10-14** (`evals/judge/2026-10-14/`), on the references before LAB-201, 30 baseline answers graded by the developer: exact agreement 0.90, within one point 0.93, agreement on "4 or more" 0.97, quadratic weighted kappa **0.90**, Spearman 0.85. The judge applies the rubric as a person does. The three disagreements say more about the references than about the judge: twice the judge followed a reference the person knew to be wrong (a passing position taken for an overtake; see "Limits"), and graded higher. The rubric stays as it is; the strategy references are what must improve (LAB-146's review). A second round on the references of LAB-201 and the false premise rule is in `evals/judge/2026-10-15/`, to grade.

## Limits

- **The judge and Ragas run on `chat-pro`, the model of the systems they score.** A model grading its own kind of answers can be lenient with its own errors. The calibration against a person measures that; a judge on another provider is the fix if it shows.
- **The rate limit sets the duration.** The f1 key allows 60 requests a minute and a case takes 3 to 6 calls: the 248 cases of the test set take about 25 minutes, over the 15 aimed at. The evaluation key of LAB-195 (300 a minute) brings it under. Until then, `--sample` gives a quick look; the client waits out a 429 instead of counting a failure.
- **Strategy references are a rule's reading of the data** (`evals/README.md`): the judge's grade is only as good as the reference. The calibration found the first ones too thin and sometimes wrong: penalties served at a stop taken for slow stops, a neutralization not named, a stop compared with the wrong stop of the rival, a passing position taken for an overtake, questions that always assumed the premise. LAB-201 rewrote the rule on each point; the calibration of 2026-10-14 was measured on the old references.
- **`retrieval` and `regulation` metrics measure the passages the system retrieved.** For the baseline, the passages themselves; the ablation of the production pipeline, stage by stage, is `just rag-eval`.
