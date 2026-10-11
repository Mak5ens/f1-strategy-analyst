import httpx
import pytest

from core.http import RateLimitedClient


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def client(
    responses: list[httpx.Response | Exception],
    fake: FakeTime,
    *,
    min_interval: float = 0.5,
    max_retries: int = 5,
    backoff: float = 2.0,
) -> RateLimitedClient:
    remaining = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        answer = remaining.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return RateLimitedClient(
        "https://api.test",
        min_interval=min_interval,
        max_retries=max_retries,
        backoff=backoff,
        transport=httpx.MockTransport(handler),
        sleep=fake.sleep,
        clock=fake.clock,
    )


def test_calls_are_spaced_by_the_minimum_interval() -> None:
    fake = FakeTime()
    api = client([httpx.Response(200, json=[1]), httpx.Response(200, json=[2])], fake, min_interval=0.5)
    assert api.get_json("/a") == [1]
    fake.now += 0.2
    assert api.get_json("/b") == [2]
    assert fake.sleeps == [pytest.approx(0.3)]


def test_a_429_waits_for_retry_after_then_retries() -> None:
    fake = FakeTime()
    api = client([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"ok": True})], fake)
    assert api.get_json("/a") == {"ok": True}
    assert 7.0 in fake.sleeps


def test_server_errors_back_off_exponentially() -> None:
    fake = FakeTime()
    api = client(
        [httpx.Response(503), httpx.Response(502), httpx.Response(200, json=[])], fake, backoff=1.0, min_interval=0
    )
    assert api.get_json("/a") == []
    assert fake.sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries() -> None:
    fake = FakeTime()
    api = client([httpx.Response(503)] * 3, fake, max_retries=2, min_interval=0)
    with pytest.raises(httpx.HTTPStatusError):
        api.get_json("/a")


def test_network_errors_are_retried() -> None:
    fake = FakeTime()
    api = client([httpx.ConnectError("down"), httpx.Response(200, json=[])], fake, min_interval=0)
    assert api.get_json("/a") == []


def test_404_is_none_only_when_allowed() -> None:
    fake = FakeTime()
    api = client([httpx.Response(404), httpx.Response(404)], fake)
    assert api.get_json("/a", missing_ok=True) is None
    with pytest.raises(httpx.HTTPStatusError):
        api.get_json("/a")


def test_client_errors_are_not_retried() -> None:
    fake = FakeTime()
    api = client([httpx.Response(400)], fake)
    with pytest.raises(httpx.HTTPStatusError):
        api.get_json("/a")
    assert fake.sleeps == []
