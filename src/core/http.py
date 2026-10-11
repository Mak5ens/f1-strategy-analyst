"""HTTP client for public JSON APIs: spaces its calls and retries on rate limits and server errors."""

import email.utils
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class RateLimitedClient:
    """GET JSON from one API without breaking its rate limits.

    Calls are spaced by at least `min_interval` seconds. A 429 or 5xx answer, or a network error, is retried
    up to `max_retries` times, waiting for the server's `Retry-After` when it sends one, else an exponential backoff.
    """

    def __init__(
        self,
        base_url: str,
        *,
        min_interval: float,
        max_retries: int = 5,
        backoff: float = 2.0,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url, timeout=timeout, headers=headers, transport=transport, follow_redirects=True
        )
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None

    def get_json(self, path: str, params: dict[str, Any] | None = None, *, missing_ok: bool = False) -> Any:
        """Return the decoded body. With `missing_ok`, a 404 returns None instead of raising."""
        response = self.request("GET", path, params=params, missing_ok=missing_ok)
        return None if response is None else response.json()

    def request(self, method: str, path: str, *, missing_ok: bool = False, **options: Any) -> httpx.Response | None:
        """Any call, with the same spacing and retries. With `missing_ok`, a 404 returns None instead of raising."""
        for attempt in range(self._max_retries + 1):
            self._wait_turn()
            try:
                response = self._client.request(method, path, **options)
            except httpx.TransportError:
                if attempt == self._max_retries:
                    raise
                self._sleep(self._backoff * 2.0**attempt)
                continue
            if response.status_code == 404 and missing_ok:
                return None
            if response.status_code in RETRYABLE_STATUSES and attempt < self._max_retries:
                self._sleep(self._retry_delay(response, attempt))
                continue
            response.raise_for_status()
            return response
        raise AssertionError("unreachable: the last attempt returns or raises")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RateLimitedClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _wait_turn(self) -> None:
        now = self._clock()
        if self._last_call is not None and (elapsed := now - self._last_call) < self._min_interval:
            self._sleep(self._min_interval - elapsed)
            now += self._min_interval - elapsed
        self._last_call = now

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return float(retry_after)
        if retry_after:
            try:
                date = email.utils.parsedate_to_datetime(retry_after)
            except (TypeError, ValueError):
                pass
            else:
                if date.tzinfo is not None:
                    return max(0.0, float((date - datetime.now(UTC)).total_seconds()))
        return self._backoff * 2.0**attempt
