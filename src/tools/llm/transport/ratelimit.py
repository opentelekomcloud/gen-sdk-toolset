"""Rate limiting: one instance per endpoint, state shared across threads."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import replace
from typing import Any

from tools.llm.transport.base import RATE_LIMITED, Transport, TransportResult


class RateLimiter:
    def __init__(
        self,
        inner: Transport,
        *,
        concurrency: int = 8,
        min_interval: float = 0.0,
        retry_after_ceiling: float = 30.0,
        attempts: int = 2,
        default_backoff: float = 2.0,
        jitter: float = 0.25,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self._inner = inner
        self._slots = threading.Semaphore(concurrency)
        self._lock = threading.Lock()
        self._cooldown_until = 0.0
        self._last_send_at: float | None = None
        # 429s without Retry-After, in a row, across calls: the endpoint is not
        # saying how long, so the pause doubles per refusal and the first answered
        # request resets it. Counted per limiter, not per send(): a caller that
        # makes one attempt per send() must not get the same 2-second pause twelve
        # times over.
        self._strikes = 0
        self._min_interval = min_interval
        self._ceiling = retry_after_ceiling
        self._attempts = attempts
        self._default_backoff = default_backoff
        self._jitter = jitter

    def send(
        self, path: str, body: dict[str, Any], *, timeout: float
    ) -> TransportResult:
        result: TransportResult | None = None
        for attempt in range(1, self._attempts + 1):
            # The slot is held until the cooldown is announced, otherwise a waiter
            # takes the freed slot and sends against stale state.
            with self._slots:
                pause = self._await_ready()
                if pause is not None:
                    # The endpoint asked for a longer pause than we are willing to
                    # sit through: refuse right here, without a network call, rather
                    # than send into a known 429 - and without sleeping past the
                    # ceiling.
                    return TransportResult(
                        status=RATE_LIMITED,
                        retry_after=pause,
                        sent=False,
                        error=f"endpoint asked for a {pause:g}s pause > ceiling "
                        f"{self._ceiling:g}s - not sent",
                    )

                result = self._inner.send(path, body, timeout=timeout)

                if result.status != RATE_LIMITED:
                    with self._lock:
                        self._strikes = 0
                    return result

                wait = result.retry_after
                if wait is None:
                    with self._lock:
                        self._strikes += 1
                        strikes = self._strikes
                    # 2, 4, 8, 16, then the ceiling: never above it, so a run of
                    # refusals slows down instead of stopping the caller outright.
                    wait = min(
                        self._default_backoff * 2 ** (strikes - 1), self._ceiling
                    )

                # The endpoint's demand is shared state even when it is more than
                # we will wait: otherwise every other thread sends and collects its
                # own 429.
                self._announce_cooldown(wait)

                if wait > self._ceiling:
                    return replace(
                        result,
                        error=f"Retry-After {wait:g}s > ceiling {self._ceiling:g}s",
                    )

            if attempt >= self._attempts:
                return replace(result, error=f"rate limited after {attempt} attempts")

        assert result is not None
        return result

    def _await_ready(self) -> float | None:
        """Wait for the shared cooldown and the pacing gap.

        Returns None when it is fine to send, or the remaining pause when that
        pause exceeds the ceiling. The ceiling is re-checked on every turn of the
        loop, under the lock: another thread may announce a long cooldown while
        this one is already waiting on a short one, and it must not sleep the
        whole remainder.
        """
        while True:
            with self._lock:
                now = time.monotonic()
                remaining = self._cooldown_until - now
                if remaining > self._ceiling:
                    return remaining
                if remaining <= 0:
                    gap = (
                        0.0
                        if self._last_send_at is None
                        else self._last_send_at + self._min_interval - now
                    )
                    if gap <= 0:
                        self._last_send_at = now
                        return None
                    wait = gap
                else:
                    wait = remaining + random.random() * self._jitter
            time.sleep(max(wait, 0.0))

    def _announce_cooldown(self, seconds: float) -> None:
        with self._lock:
            until = time.monotonic() + seconds
            if until > self._cooldown_until:
                self._cooldown_until = until
