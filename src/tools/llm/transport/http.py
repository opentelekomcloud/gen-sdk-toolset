"""HTTP transport: one instance per endpoint."""

from __future__ import annotations

import http.client
import json
import random
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.request import urlopen

from tools.llm.transport.base import (
    HTTP_ERROR,
    NETWORK,
    OK,
    RATE_LIMITED,
    TIMEOUT,
    TransportResult,
)

_TRANSIENT_CODES = (503, 504)


def parse_retry_after(value: str | None) -> float | None:
    """Seconds a ``Retry-After`` header asks for: delta-seconds or an HTTP date."""
    if not value:
        return None
    text = value.strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    return max(0.0, when.timestamp() - time.time())


class HttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        attempts: int = 2,
        backoff: float = 0.5,
        jitter: float = 0.25,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._attempts = attempts
        self._backoff = backoff
        self._jitter = jitter

    def send(
        self, path: str, body: dict[str, Any], *, timeout: float
    ) -> TransportResult:
        started = time.monotonic()
        last = TransportResult(status=NETWORK, error="request was never made")
        for attempt in range(1, self._attempts + 1):
            last = self._once(path, body, timeout=timeout, started=started)
            if not _worth_repeating(last):
                return last
            if attempt < self._attempts:
                time.sleep(self._backoff * attempt + random.random() * self._jitter)
        return last

    def _once(
        self, path: str, body: dict[str, Any], *, timeout: float, started: float
    ) -> TransportResult:
        request = urllib.request.Request(
            url=f"{self.base_url}/{path.lstrip('/')}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        # Which side of the send a failure lands on decides whether it may be
        # repeated. urllib wraps connect/send errors in URLError: the request never
        # reached the server whole, repeating it is free. Everything raised bare -
        # a timeout, a reset, a garbled status line, a cut-off body - happened while
        # waiting for or reading the answer: the request was delivered, and a
        # finished generation may be hiding behind the failure. Those are returned
        # with sent=True and not repeated.
        try:
            with urlopen(request, timeout=timeout) as response:
                http_status = getattr(response, "status", 200) or 200
                headers = _headers_of(response)
                try:
                    raw = _as_bytes(response.read())
                except http.client.IncompleteRead as error:
                    return TransportResult(
                        status=NETWORK,
                        http_status=http_status,
                        headers=headers,
                        elapsed_ms=_elapsed(started),
                        sent=True,
                        error=f"IncompleteRead: {error}",
                    )
                return TransportResult(
                    status=OK,
                    raw=raw,
                    http_status=http_status,
                    headers=headers,
                    elapsed_ms=_elapsed(started),
                    sent=True,
                )
        except urllib.error.HTTPError as error:
            return _from_http_error(error, started=started)
        except urllib.error.URLError as error:
            reason = error.reason
            status = TIMEOUT if isinstance(reason, TimeoutError) else NETWORK
            return TransportResult(
                status=status,
                elapsed_ms=_elapsed(started),
                sent=False,
                error=str(reason),
            )
        except TimeoutError as error:
            return TransportResult(
                status=TIMEOUT,
                elapsed_ms=_elapsed(started),
                sent=True,
                error=str(error) or "read timeout",
            )
        except http.client.HTTPException as error:
            # BadStatusLine, RemoteDisconnected, ...: HTTPException is not an
            # OSError and would otherwise escape the port as a traceback.
            return TransportResult(
                status=NETWORK,
                elapsed_ms=_elapsed(started),
                sent=True,
                error=f"{type(error).__name__}: {error}",
            )
        except OSError as error:
            return TransportResult(
                status=NETWORK,
                elapsed_ms=_elapsed(started),
                sent=True,
                error=str(error),
            )


def _from_http_error(
    error: urllib.error.HTTPError, *, started: float
) -> TransportResult:
    headers = _headers_of(error)
    retry_after = parse_retry_after(_header(headers, "Retry-After"))
    code = int(error.code)
    common: dict[str, Any] = dict(
        raw=_read_quietly(error),
        http_status=code,
        headers=headers,
        elapsed_ms=_elapsed(started),
        sent=True,
        error=f"HTTP {code}",
    )
    # Backpressure goes up to the limiter, never retried here.
    if code == 429 or (code in _TRANSIENT_CODES and retry_after is not None):
        return TransportResult(status=RATE_LIMITED, retry_after=retry_after, **common)
    return TransportResult(status=HTTP_ERROR, **common)


def _worth_repeating(result: TransportResult) -> bool:
    # Only a request the server demonstrably never received whole is sent again.
    # Any failure after the send - timeout, reset, cut-off or garbled response -
    # may hide a generation that was already finished; a second attempt would run
    # it twice. 503/504 without Retry-After: the server itself says it did not
    # serve the request.
    if result.status in (TIMEOUT, NETWORK):
        return not result.sent
    return result.status == HTTP_ERROR and result.http_status in _TRANSIENT_CODES


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _header(headers: dict[str, str], name: str) -> str | None:
    # Header names are case-insensitive.
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def _headers_of(response: Any) -> dict[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {}
    try:
        return {str(k): str(v) for k, v in headers.items()}
    except AttributeError:
        return {}


def _read_quietly(error: urllib.error.HTTPError) -> bytes:
    try:
        return _as_bytes(error.read())
    except Exception:  # an error body that cannot be read is simply absent
        return b""


def _as_bytes(raw: Any) -> bytes:
    if raw is None:
        return b""
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, bytearray):
        return bytes(raw)
    if isinstance(raw, str):
        return raw.encode("utf-8")
    return bytes(raw)
