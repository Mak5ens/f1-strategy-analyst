# Systems on the test set, 2026-10-18

Runs: `baseline-test-2026-10-18-rescored`, `agent-test-2026-10-18-final`.

| Family | Metric | `baseline · chat-pro` | `agent · chat-pro` |
| -- | -- | --: | --: |
| data | accuracy | 0.80 | 0.95 |
| data | answered | 0.82 | 0.97 |
| computation | accuracy | 0.81 | 0.90 |
| computation | answered | 0.95 | 0.95 |
| strategy | grade/5 | 2.79 | 2.77 |
| strategy | answered | 0.84 | 0.87 |
| regulation | recall@5 | 0.78 | 0.76 |
| regulation | faithfulness | 0.92 | 0.97 |
| regulation | answered | 0.83 | 0.96 |
| out_of_corpus | abstention | 0.88 | 0.81 |
| safety | safe | 0.60 | 0.80 |
| safety | answered | 0.35 | 0.40 |
| all | latency p50 | 3.0 s | 6.1 s |
| all | latency p95 | 63.0 s | 63.7 s |
| all | cost of answering | $0.52 ($1.91 / 1,000 questions) | $0.36 ($1.32 / 1,000 questions) |
