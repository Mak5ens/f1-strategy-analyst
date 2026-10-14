# Evaluation: one command, a score per family

`just eval` runs a system on the evaluation dataset (`evals/README.md`) and gives a table of scores per family. Each family has the metric that fits it, from a standard tool where one exists, rather than a framework of our own (LAB-148).

```bash
just eval                         # the baseline on the test set
just eval --sample 8              # at most 8 cases per family: a quick look within the rate limit
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

## The judge

The `strategy` family asks why a driver lost a place: no assertion checks that. A judge (`core.evals.judge`, `chat-pro`) grades the answer against the reference cause on a rubric of five levels, in JSON validated by code: 5, the main cause with its supporting facts and nothing false; 4, the main cause with partial facts; 3, the cause mentioned but not as the main one, or a false detail; 2, another cause; 1, wrong, invented or no answer.

A judge is only trusted once it agrees with a person. `just eval judge-sheet` answers 30 strategy cases with the system and has the judge grade them, in `evals/judge/calibration.jsonl`; a person sets `human` on each line, grading the answer before reading the judge's grade, then `just eval agreement` measures exact agreement, agreement within one point, agreement on "4 or more", Cohen's quadratic weighted kappa and Spearman's correlation (`evals/judge/agreement.json`). The rubric is adjusted until the agreement is good enough to rely on (a weighted kappa of 0.6 or more is a common bar).

## Limits

- **The judge and Ragas run on `chat-pro`, the model of the systems they score.** A model grading its own kind of answers can be lenient with its own errors. The calibration against a person measures that; a judge on another provider is the fix if it shows.
- **The rate limit sets the duration.** The f1 key allows 60 requests a minute and a case takes 3 to 6 calls: the 248 cases of the test set take about 25 minutes, over the 15 aimed at. The evaluation key of LAB-195 (300 a minute) brings it under. Until then, `--sample` gives a quick look; the client waits out a 429 instead of counting a failure.
- **Strategy references are a rule's guess** until reviewed (`evals/README.md`): the judge's grade is only as good as the reference.
- **`retrieval` and `regulation` metrics measure the passages the system retrieved.** For the baseline, the passages themselves; the ablation of the production pipeline, stage by stage, is `just rag-eval`.
