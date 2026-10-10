# Evaluation

The test set and the evaluation harness will live here (milestone 4.2):

- `datasets/`: the cases, each with its family, its expected answer and where that answer comes from (LAB-146).
- the configuration of promptfoo, Ragas and the calibrated LLM judge (LAB-148), run by `just eval`.

The harness code belongs to `src/core/` (ADR-011): only the datasets and the thresholds are specific to F1.
