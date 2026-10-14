# Session summaries: a season through the job queue

`just season-jobs 2025` writes a strategy summary of every session of a season (practices, qualifying, sprint, race: 120 in 2025), as one asynchronous job each on the job queue of [llmops-platform](https://github.com/Mak5ens/llmops-platform).
It is the workload of the platform's season benchmark (LAB-139): a real volume of model calls, produced by the app, run by the workers that KEDA scales from zero.

```bash
just season-jobs 2025                  # every session of 2025 in the lake, summaries on chat-pro
just season-jobs 2025 --round 16       # one weekend
just season-jobs 2025 --simulate       # the same 120 jobs, simulated by the worker: no model call
```

It needs llmops-gateway's stack (`just gateway-up` there: RabbitMQ, the worker, the gateway) and the season in the lake (`just ingest 2025`).

## How it runs

1. **Facts, from the lake** (`f1/jobs/facts.py`). For each session, code computes what the summary may say:
   - practice: the order of the best laps, the gaps to the fastest and to the car ahead, laps done, the longest run on one set of tyres (clean laps within 112% of the driver's best, so that cool-down laps do not count);
   - qualifying: the order, each part's time, the gaps to pole and to the car ahead, who went out in Q1 or Q2, deleted laps;
   - race: the result, the grid and places gained, pit stops and tyres, the fastest lap, the safety cars and red flags (the `neutralizations` tool);
   - all: the weather and the red flags.
2. **One job per session** (`f1/jobs/__init__.py`): the facts as delimited data in the prompt, `chat-pro`, at most 1,024 tokens. Published to the exchange `jobs` with the routing key `inference`, persistent, with a `reply_to` and a W3C `traceparent` (one trace per batch, a span per job).
3. **Collection** (`core/jobs.py`): replies come back on the durable queue `f1.season-jobs.replies`. A job that fails for good gets no reply: the collector finds it in the dead letter queue `jobs.inference.dead`, with RabbitMQ's reason (`rejected`: the worker gave up at once; `delivery_limit`: it failed three times). The other jobs of that queue are left there. The run ends when every job is accounted for, or after 5 minutes with nothing back (`missing`).
4. **Storage**: each summary goes to the lake as it comes, `session_summaries/2025/16-Q.json`, with its facts, its usage and the result of the checks; the account of the batch to `session_summaries/2025/_batches/<batch>.json`.

The job format is llmops-gateway's (`worker/README.md`). The worker calls the gateway with the f1 key as end user `llmops-worker`, so the cost of the jobs stands apart from the app's own calls in the gateway's metrics.

## No number from the model alone

The model is given the numbers and asked to compute none. Then code checks each summary:

- **Numbers**: every number of the summary must be in its facts, as written or rounded ("0.08 s" for 0.077). Lap times are read as seconds, positions as "P3" too.
- **Names**: every name of two capitalized words or more (a driver, a team) must be in the facts. Drivers are given in full, from the results: given "ANT", the model wrote "Antonio Giovinazzi, sur Mercedes".

What fails is kept with the summary, as `unverified_numbers` and `unverified_names`, and counted at the end of the run: the summary is stored, flagged, for a human or the agent's review to decide. Numbers written in words ("deux arrêts") and a name said of the wrong thing (a driver given another's team) are not checked.

## Measured on 2025

Locally, on llmops-gateway's stack (one worker):

| | First run | After the fixes |
| -- | -- | -- |
| Jobs | 120 done | 120 done |
| Time | 288 s | 276 s, 26 jobs a minute |
| Summaries flagged | 26 of 120 | 5 of 120 |

The first run's flags were mostly practice positions ("les 3 premiers"), which the facts did not hold yet, and two real faults: gaps between two drivers the model computed itself (0.011 s, 0.022 s). With the position and the gap to the car ahead in the facts, no number is flagged. The 5 flags left are one false positive: the model writes the Saudi Arabian Grand Prix in French, "Arabie Saoudite".

A season costs about 223,000 prompt tokens and 39,000 completion tokens: about 5 cents on `chat-pro` (Mistral Small 3.2), under the f1 team's budget and the gateway's Scaleway cap. A job takes 2.3 s at the median. With one local worker, the worker sets the pace; with several, the f1 key's limit does (60 requests and 100,000 tokens a minute, so about 25 to 40 summaries a minute): that is what LAB-139 measures.

On the cluster, use `chat-pro`: `chat-medium` there is a 0.5b model standing in, which does not write a credible summary. Set `JOBS_AMQP_URL` to the platform's job queue.
