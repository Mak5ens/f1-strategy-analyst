"""Batches of model calls through the platform's job queue: publish them, then collect each answer or its failure.

llmops-platform runs a RabbitMQ queue and workers (llmops-gateway's `worker/`, scaled by KEDA from zero) that call
the gateway with the team's key. A job is a JSON message published to the exchange `jobs` with the routing key
`inference`, its format in llmops-gateway/worker/README.md. A job with a `reply_to` gets its result on that queue,
with its `correlation_id`. A job that fails for good (an invalid job, three failures) is dead-lettered to
`jobs.inference.dead`, and gets no reply: the collector looks for it there.

Every message of a batch carries the batch's id in its `correlation_id`, so the replies of an earlier batch left in
the durable reply queue are told apart, and a W3C `traceparent` of one trace per batch, which the worker continues.
"""

import asyncio
import json
import logging
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractQueue
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("core.jobs")


class JobSettings(BaseSettings):
    """Read from the environment (or `.env`) with the `JOBS_` prefix."""

    model_config = SettingsConfigDict(env_prefix="JOBS_", env_file=".env", extra="ignore")

    # llmops-gateway's compose stack publishes RabbitMQ on 5673; on the cluster, the platform's job-queue secret.
    amqp_url: SecretStr = SecretStr("amqp://jobs:local-dev-password@localhost:5673/")
    exchange: str = "jobs"
    routing_key: str = "inference"
    dead_letter_queue: str = "jobs.inference.dead"
    # How often the dead letter queue is searched for the batch's jobs while replies come in.
    dead_letter_scan_seconds: float = 15.0


@dataclass(frozen=True)
class Job:
    id: str
    body: dict[str, Any]  # the job as the worker reads it: team, alias, messages, max_tokens, or simulate


Status = Literal["done", "dead", "refused", "missing"]


@dataclass
class Result:
    id: str
    status: Status
    reply: dict[str, Any] = field(default_factory=dict)  # the worker's answer: content, usage, seconds...
    reason: str = ""  # for a dead job: why RabbitMQ dead-lettered it, and after how many deliveries


@dataclass
class Report:
    batch: str
    trace_id: str
    results: dict[str, Result]
    seconds: float

    def count(self, status: Status) -> int:
        return sum(result.status == status for result in self.results.values())

    @property
    def tokens(self) -> int:
        return sum(int((result.reply.get("usage") or {}).get("total_tokens", 0)) for result in self.results.values())

    def summary(self) -> str:
        counts = ", ".join(f"{self.count(status)} {status}" for status in ("done", "dead", "refused", "missing"))
        rate = self.count("done") / self.seconds * 60 if self.seconds else 0.0
        return (
            f"{len(self.results)} jobs in {self.seconds:.0f} s ({rate:.1f} done a minute): {counts}; "
            f"{self.tokens} tokens; trace {self.trace_id}"
        )


class Ledger:
    """What became of each job of a batch: no AMQP here, so it is tested without a broker."""

    def __init__(self, batch: str, jobs: Sequence[Job]) -> None:
        self.batch = batch
        self.results: dict[str, Result] = {job.id: Result(job.id, "missing") for job in jobs}

    def correlation_id(self, job: Job) -> str:
        return f"{self.batch}/{job.id}"

    def job_id(self, correlation_id: str | None) -> str | None:
        """The job of this batch a message is about, None for another batch's."""
        batch, _, job_id = (correlation_id or "").partition("/")
        return job_id if batch == self.batch and job_id in self.results else None

    def refused(self, job_id: str, reason: str) -> None:
        self.results[job_id] = Result(job_id, "refused", reason=reason)

    def replied(self, correlation_id: str | None, reply: dict[str, Any]) -> Result | None:
        job_id = self.job_id(correlation_id)
        if job_id is None or self.results[job_id].status != "missing":
            return None
        self.results[job_id] = Result(job_id, "done", reply=reply)
        return self.results[job_id]

    def dead(self, correlation_id: str | None, headers: dict[str, Any]) -> Result | None:
        job_id = self.job_id(correlation_id)
        if job_id is None or self.results[job_id].status != "missing":
            return None
        self.results[job_id] = Result(job_id, "dead", reason=dead_letter_reason(headers))
        return self.results[job_id]

    def count(self, status: Status) -> int:
        return sum(result.status == status for result in self.results.values())

    @property
    def pending(self) -> int:
        return self.count("missing")


def dead_letter_reason(headers: dict[str, Any]) -> str:
    """RabbitMQ's account of a dead-lettered message: `rejected` (the worker gave up on it at once: an invalid job,
    a refused key or alias, a budget spent) or `delivery_limit` (it failed on every attempt), and after how many
    deliveries (`x-acquired-count` of a quorum queue)."""
    reason = str(headers.get("x-first-death-reason") or "unknown")
    deliveries = headers.get("x-acquired-count", headers.get("x-delivery-count"))
    return f"{reason} after {int(deliveries)} deliveries" if deliveries is not None else reason


def traceparent(trace_id: str) -> str:
    """A W3C traceparent in the batch's trace, with a span of its own for each job."""
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"


async def run_batch(
    jobs: Sequence[Job],
    *,
    reply_queue: str,
    settings: JobSettings | None = None,
    idle_timeout: float = 300.0,
    on_result: Callable[[Result], None] = lambda result: None,
) -> Report:
    """Publish the jobs, then wait until each is answered or dead-lettered, or until nothing has come back for
    `idle_timeout` seconds: the jobs still unaccounted for are then `missing`. `on_result` sees each result as it
    comes, to store it at once."""
    settings = settings or JobSettings()
    batch, trace_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}", secrets.token_hex(16)
    ledger = Ledger(batch, jobs)
    start = time.monotonic()
    connection = await aio_pika.connect_robust(settings.amqp_url.get_secret_value())
    async with connection:
        channel = await connection.channel(publisher_confirms=True)
        # Durable, so that answers survive a restart of the collector; RabbitMQ 4 refuses transient shared queues.
        replies = await channel.declare_queue(reply_queue, durable=True)
        await _publish(channel, settings, jobs, ledger, reply_queue, trace_id)
        log.info("batch %s: %d jobs published, trace %s", batch, len(jobs) - ledger.count("refused"), trace_id)
        await _collect(channel, replies, settings, ledger, idle_timeout, on_result)
    return Report(batch, trace_id, ledger.results, time.monotonic() - start)


async def _publish(
    channel: AbstractChannel,
    settings: JobSettings,
    jobs: Sequence[Job],
    ledger: Ledger,
    reply_queue: str,
    trace_id: str,
) -> None:
    exchange = await channel.get_exchange(settings.exchange)  # declared by the platform: fail if missing
    for job in jobs:
        message = aio_pika.Message(
            json.dumps(job.body).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            correlation_id=ledger.correlation_id(job),
            reply_to=reply_queue,
            headers={"traceparent": traceparent(trace_id)},
        )
        try:
            # mandatory: an unroutable job is returned rather than lost. With publisher confirms, a queue that is
            # full (overflow reject-publish) nacks it.
            await exchange.publish(message, routing_key=settings.routing_key, mandatory=True)
        except (aio_pika.exceptions.DeliveryError, aio_pika.exceptions.PublishError) as error:
            ledger.refused(job.id, f"{type(error).__name__}: {error}")


async def _collect(
    channel: AbstractChannel,
    replies: AbstractQueue,
    settings: JobSettings,
    ledger: Ledger,
    idle_timeout: float,
    on_result: Callable[[Result], None],
) -> None:
    last_news = time.monotonic()
    next_scan = 0.0
    while ledger.pending:
        message = await replies.get(no_ack=False, fail=False, timeout=5)
        if message is not None:
            await message.ack()
            if result := ledger.replied(message.correlation_id, _json(message)):
                on_result(result)
                last_news = time.monotonic()
            continue
        if time.monotonic() >= next_scan:
            for result in await _scan_dead_letters(channel, settings, ledger):
                on_result(result)
                last_news = time.monotonic()
            next_scan = time.monotonic() + settings.dead_letter_scan_seconds
        if time.monotonic() - last_news > idle_timeout:
            log.warning("nothing back for %.0f s: %d jobs left missing", idle_timeout, ledger.pending)
            return
        await asyncio.sleep(1)


async def _scan_dead_letters(channel: AbstractChannel, settings: JobSettings, ledger: Ledger) -> list[Result]:
    """Take this batch's jobs out of the dead letter queue, and leave the others there: they are held unacknowledged
    while the queue is read through (a held message is not delivered again, so the read ends), then given back.
    The message count of a passive declare is not used: on a robust channel it came back stale."""
    queue = await channel.declare_queue(settings.dead_letter_queue, passive=True)
    found, others = [], []
    while (message := await queue.get(no_ack=False, fail=False)) is not None:
        if result := ledger.dead(message.correlation_id, dict(message.headers or {})):
            await message.ack()
            found.append(result)
        else:
            others.append(message)
    for message in others:
        await message.nack(requeue=True)
    return found


def _json(message: AbstractIncomingMessage) -> dict[str, Any]:
    try:
        body = json.loads(message.body)
    except ValueError:
        return {"content": message.body.decode(errors="replace")}
    return body if isinstance(body, dict) else {"content": body}
