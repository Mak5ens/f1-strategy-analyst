"""Session summary jobs against llmops-gateway's stack: its RabbitMQ, its worker, the gateway, and the lake.

- A batch gets each job's answer, or finds it in the dead letter queue with RabbitMQ's reason.
- A real session's summary comes back, is stored with its facts, and its numbers are all in them.
"""

import asyncio
import socket
from urllib.parse import urlparse

import pytest

from core.jobs import Job, JobSettings, run_batch
from core.lake import Lake
from f1.data import connect
from f1.jobs import REPLY_QUEUE
from f1.jobs.season import build_jobs, store, summary_key

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def broker() -> None:
    url = urlparse(JobSettings().amqp_url.get_secret_value())
    try:
        socket.create_connection((url.hostname or "localhost", url.port or 5672), timeout=2).close()
    except OSError:
        pytest.skip("RabbitMQ unreachable: run `just gateway-up` in llmops-gateway")


def test_each_job_is_answered_or_found_dead_with_its_reason() -> None:
    jobs = [
        Job("ok", {"id": "ok", "team": "f1", "simulate": {"seconds": 0.1}}),
        Job("invalid", {"id": "invalid", "team": "f1"}),  # no alias, no messages: dead-lettered at once
    ]
    report = asyncio.run(run_batch(jobs, reply_queue=REPLY_QUEUE, idle_timeout=60))

    assert report.results["ok"].status == "done"
    assert report.results["ok"].reply["simulated"] is True
    assert report.results["invalid"].status == "dead"
    assert report.results["invalid"].reason.startswith("rejected")


def test_a_session_summary_is_stored_with_its_facts_and_checked() -> None:
    lake = Lake()
    if not connect(lake).execute("SELECT 1 FROM sessions WHERE season = 2025 AND round = 16 AND session = 'Q'").fetchall():
        pytest.skip("2025 not in the lake: run `just ingest 2025`")
    jobs, facts = build_jobs(lake, 2025, [16])
    [qualifying] = [job for job in jobs if job.id == "2025-r16-Q"]

    report = asyncio.run(run_batch([qualifying], reply_queue=REPLY_QUEUE, idle_timeout=120))
    result = report.results[qualifying.id]
    assert result.status == "done", result.reason
    unverified = store(lake, 2025, result, facts[qualifying.id])

    stored = lake.read_json(summary_key(2025, 16, "Q"))
    assert stored is not None
    assert "Verstappen" in stored["summary"]  # pole of the 2025 Italian Grand Prix
    assert stored["facts"]["classification"][0]["q3"] == "1:18.792"
    assert stored["unverified_numbers"] == [], unverified
