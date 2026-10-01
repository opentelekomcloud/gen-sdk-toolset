"""Rate limiter of the LLM client.

* A 429 announces a cooldown every thread waits out, not just the one refused.
* 429s without Retry-After back off exponentially across calls, up to a ceiling.
* A pause beyond the ceiling is refused on the spot, unsent, never slept through.
* Concurrency and the pacing gap between starts hold under threads.
"""

from __future__ import annotations

import threading
import time

import pytest

from tools.llm.transport import ratelimit
from tools.llm.transport.base import OK, RATE_LIMITED, TransportResult
from tools.llm.transport.ratelimit import RateLimiter


class FakeClock:
    """Stands in for the ``time`` module inside the limiter: sleeping advances it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []
        self.on_sleep = None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep()


class FixedRandom:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


class Inner:
    """The wrapped transport: answers with the queued outcomes, repeating the
    last one, and records when each call started and how many ran at once."""

    def __init__(self, *outcomes, monotonic=time.monotonic, work=0.0):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.started_at: list[float] = []
        self._monotonic = monotonic
        self._work = work
        self._lock = threading.Lock()
        self.in_flight = 0
        self.peak_in_flight = 0

    def send(self, path, body, *, timeout):
        with self._lock:
            self.calls += 1
            self.started_at.append(self._monotonic())
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            if self._work:
                time.sleep(self._work)
            index = min(self.calls - 1, len(self.outcomes) - 1)
            return self.outcomes[index]
        finally:
            with self._lock:
                self.in_flight -= 1


def limited(retry_after=None):
    return TransportResult(
        status=RATE_LIMITED, http_status=429, retry_after=retry_after, error="429"
    )


def fine():
    return TransportResult(status=OK, http_status=200, raw=b'{"ok": true}')


def send(limiter: RateLimiter) -> TransportResult:
    return limiter.send("chat", {}, timeout=45)


def send_from_threads(limiter: RateLimiter, count: int) -> None:
    threads = [threading.Thread(target=send, args=(limiter,)) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(ratelimit, "time", fake)
    monkeypatch.setattr(ratelimit, "random", FixedRandom(0.0))
    return fake


# --- pass-through --- #


def test_success_goes_straight_through():
    inner = Inner(fine())
    limiter = RateLimiter(inner, concurrency=2)
    assert send(limiter).status == OK
    assert inner.calls == 1


def test_non_rate_limit_failures_are_not_retried_here():
    inner = Inner(TransportResult(status="network", error="reset"))
    limiter = RateLimiter(inner, attempts=3)
    assert send(limiter).status == "network"
    assert inner.calls == 1


# --- cooldown --- #


def test_a_429_is_retried_only_after_its_retry_after(clock):
    inner = Inner(limited(retry_after=5), fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=2, jitter=0.0)
    assert send(limiter).status == OK
    assert inner.calls == 2
    assert inner.started_at[1] - inner.started_at[0] >= 5.0


def test_the_next_call_waits_out_a_cooldown_another_call_announced(clock):
    inner = Inner(limited(retry_after=9), fine(), fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=1, jitter=0.0)
    send(limiter)  # collects the 429 and announces the cooldown
    send(limiter)  # must wait it out
    assert inner.started_at[1] - inner.started_at[0] >= 9.0
    send(limiter)  # the cooldown is over: no further wait
    assert clock.slept == [9.0]


def test_without_retry_after_the_backoff_grows(clock):
    inner = Inner(limited(), limited(), fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=3, default_backoff=2.0, jitter=0.0)
    send(limiter)
    assert inner.started_at[1] - inner.started_at[0] >= 2.0
    assert inner.started_at[2] - inner.started_at[1] >= 4.0


# --- strikes: 429s without Retry-After, counted across calls --- #
#
# A caller that makes one attempt per send() would otherwise get the same
# 2-second pause for each of twelve refusals in a row. The pause each call
# announced is what the following call sleeps before it sends.


def strike_limiter(inner: Inner) -> RateLimiter:
    return RateLimiter(
        inner, attempts=1, default_backoff=2.0, retry_after_ceiling=30.0, jitter=0.0
    )


def test_the_pause_doubles_across_calls_and_stops_at_the_ceiling(clock):
    inner = Inner(limited(), monotonic=clock.monotonic)
    limiter = strike_limiter(inner)
    results = [send(limiter) for _ in range(8)]
    assert clock.slept == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]
    # 30 is not above the ceiling: every call went to the network
    assert inner.calls == 8
    assert all(result.sent for result in results)


def test_an_answered_request_resets_the_series(clock):
    inner = Inner(limited(), limited(), fine(), limited(), monotonic=clock.monotonic)
    limiter = strike_limiter(inner)
    for _ in range(5):
        send(limiter)
    # 2 after the first refusal, 4 after the second, then an answer resets the
    # series and the next refusal starts again at 2
    assert clock.slept == [2.0, 4.0, 2.0]


def test_a_retry_after_is_obeyed_as_is(clock):
    inner = Inner(limited(), limited(retry_after=5), monotonic=clock.monotonic)
    limiter = strike_limiter(inner)
    for _ in range(3):
        send(limiter)
    assert clock.slept == [2.0, 5.0]


# --- the ceiling --- #


def test_a_retry_after_above_the_ceiling_fails_immediately_but_is_still_shared(clock):
    inner = Inner(limited(retry_after=600), fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=3, retry_after_ceiling=30.0)
    result = send(limiter)
    assert result.status == RATE_LIMITED
    assert "600s > ceiling 30s" in result.error
    assert inner.calls == 1
    assert clock.slept == []
    # ...but the endpoint's demand is shared state all the same
    refused = send(limiter)
    assert refused.status == RATE_LIMITED
    assert refused.sent is False
    assert refused.retry_after == 600.0
    assert inner.calls == 1


def test_nobody_sends_into_a_pause_beyond_the_ceiling(clock):
    """The next call - this thread's or another's - is refused on the spot: no
    network request, no sleep past the ceiling, and sent=False says so."""
    inner = Inner(limited(retry_after=600), fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=1, retry_after_ceiling=30.0)
    send(limiter)
    clock.now += 100
    result = send(limiter)
    assert result.status == RATE_LIMITED
    assert result.sent is False
    assert result.retry_after == 500.0
    assert "endpoint asked for a 500s pause > ceiling 30s" in result.error
    assert inner.calls == 1
    assert clock.slept == []


def test_a_pause_announced_by_another_thread_mid_wait_is_not_slept_through(clock):
    """This thread is waiting out a short cooldown; meanwhile another thread gets
    a 429 with Retry-After 600. The wait loop must see the new cooldown on its
    next turn and refuse - not sleep the remaining ten minutes."""
    inner = Inner(fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=1, retry_after_ceiling=30.0, jitter=0.0)
    limiter._announce_cooldown(5.0)  # short: this thread will wait it out
    clock.on_sleep = lambda: limiter._announce_cooldown(600.0)  # lands mid-sleep

    result = send(limiter)
    assert result.status == RATE_LIMITED
    assert result.sent is False
    assert inner.calls == 0
    assert clock.slept == [5.0]  # only the short one; not 600 more


def test_once_the_pause_is_within_the_ceiling_sending_resumes(clock):
    inner = Inner(limited(retry_after=600), fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=1, retry_after_ceiling=30.0, jitter=0.0)
    send(limiter)
    clock.now += 580  # 20 s left: within the ceiling, so it is waited out
    result = send(limiter)
    assert result.status == OK
    assert clock.slept == [20.0]
    assert inner.calls == 2


def test_attempts_is_a_ceiling_on_rate_limited_repeats(clock):
    inner = Inner(limited(retry_after=1), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=2, jitter=0.0)
    result = send(limiter)
    assert result.status == RATE_LIMITED
    assert "rate limited after 2 attempts" in result.error
    assert inner.calls == 2


# --- jitter --- #


def test_release_from_a_cooldown_is_spread_by_jitter(clock, monkeypatch):
    monkeypatch.setattr(ratelimit, "random", FixedRandom(1.0))
    inner = Inner(limited(retry_after=4), fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, attempts=2, jitter=2.0)
    send(limiter)
    # 4 seconds of cooldown plus the whole spread: strictly longer than Retry-After
    assert inner.started_at[1] - inner.started_at[0] > 4.0


# --- the slot is held until the cooldown is announced --- #


def test_the_cooldown_is_announced_before_the_slot_is_released(clock, monkeypatch):
    order: list[str] = []
    inner = Inner(limited(retry_after=1), fine(), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, concurrency=1, attempts=1, jitter=0.0)

    announce = limiter._announce_cooldown

    def watched_announce(seconds):
        order.append("announce")
        announce(seconds)

    monkeypatch.setattr(limiter, "_announce_cooldown", watched_announce)

    slots = limiter._slots

    class WatchedSlot:
        def __enter__(self):
            slots.acquire()
            order.append("acquire")
            return self

        def __exit__(self, *exc):
            order.append("release")
            slots.release()
            return False

    monkeypatch.setattr(limiter, "_slots", WatchedSlot())

    result = send(limiter)

    assert result.status == RATE_LIMITED
    assert order == ["acquire", "announce", "release"]


def test_giving_up_on_the_ceiling_still_announces_the_pause(clock, monkeypatch):
    """Otherwise every other thread would send and collect its own 429."""
    order: list[str] = []
    inner = Inner(limited(retry_after=600), monotonic=clock.monotonic)
    limiter = RateLimiter(inner, concurrency=1, attempts=2, retry_after_ceiling=30.0)
    announce = limiter._announce_cooldown

    def watched_announce(seconds):
        order.append("announce")
        announce(seconds)

    monkeypatch.setattr(limiter, "_announce_cooldown", watched_announce)

    send(limiter)
    assert order == ["announce"]
    refused = send(limiter)
    assert refused.sent is False
    assert refused.retry_after is not None and refused.retry_after > 30.0


# --- threads: real time --- #


def test_threads_waiting_on_one_cooldown_do_not_fire_together(monkeypatch):
    cooldown = 0.25
    delays = [0.0, 0.25, 0.5, 0.75]

    class SequenceRandom:
        def __init__(self):
            self.i = 0
            self.lock = threading.Lock()

        def random(self):
            with self.lock:
                value = delays[self.i % len(delays)]
                self.i += 1
                return value

    monkeypatch.setattr(ratelimit, "random", SequenceRandom())

    class RefuseFirst:
        def __init__(self):
            self.calls = 0
            self.started_at: list[float] = []
            self.lock = threading.Lock()

        def send(self, path, body, *, timeout):
            with self.lock:
                self.calls += 1
                mine = self.calls
                self.started_at.append(time.monotonic())
            return limited(retry_after=cooldown) if mine == 1 else fine()

    inner = RefuseFirst()
    limiter = RateLimiter(
        inner, concurrency=4, min_interval=0.0, attempts=1, jitter=0.4
    )

    # one thread collects the 429 and announces the cooldown for everyone
    send(limiter)
    opened_at = limiter._cooldown_until
    assert opened_at - time.monotonic() > 0.1

    # the others arrive while the cooldown is up and wait it out together
    send_from_threads(limiter, 4)

    after = sorted(inner.started_at[1:])
    assert len(after) == 4
    assert min(after) - opened_at >= -0.01
    assert max(after) - min(after) > 0.05


def test_concurrency_is_never_exceeded():
    inner = Inner(fine(), work=0.02)
    limiter = RateLimiter(inner, concurrency=3)
    send_from_threads(limiter, 12)
    assert inner.calls == 12
    assert inner.peak_in_flight <= 3


def test_pacing_holds_between_starts_without_a_stampede():
    interval = 0.02
    inner = Inner(fine())
    limiter = RateLimiter(inner, concurrency=8, min_interval=interval)
    send_from_threads(limiter, 6)
    starts = sorted(inner.started_at)
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    assert len(gaps) == 5
    # Only a lower bound: a sleep may oversleep, never undersleep.
    assert min(gaps) >= interval - 0.005


# --- construction --- #


@pytest.mark.parametrize("field", ["concurrency", "attempts"])
def test_a_value_below_one_is_refused(field):
    with pytest.raises(ValueError, match=field):
        RateLimiter(Inner(fine()), **{field: 0})
