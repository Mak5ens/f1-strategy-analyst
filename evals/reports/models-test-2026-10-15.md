# Models on the test set, 2026-10-15

The baseline (LAB-147) with each model; the judge and Ragas stay on `chat-pro`. Runs: `models-test-2026-10-15-chat-small`, `models-test-2026-10-15-chat-medium`, `models-test-2026-10-15-chat-pro`.

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
