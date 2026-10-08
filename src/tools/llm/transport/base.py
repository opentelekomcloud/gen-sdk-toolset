"""Transport protocol and its result type.

``RateLimiter`` and ``HttpClient`` both implement ``Transport`` and stack.
Statuses here are the transport's own vocabulary; the provider adapter maps them
to ``tools.llm.port.FAILURES``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

OK = "ok"
RATE_LIMITED = "rate_limited"
TIMEOUT = "timeout"
NETWORK = "network"
HTTP_ERROR = "http_error"

STATUSES = (OK, RATE_LIMITED, TIMEOUT, NETWORK, HTTP_ERROR)


@dataclass(frozen=True)
class TransportResult:
    status: str
    #: The body as received, never parsed here.
    raw: bytes = b""
    #: ``0`` - no response at all.
    http_status: int = 0
    headers: Mapping[str, str] = field(default_factory=dict)
    elapsed_ms: int = 0
    retry_after: float | None = None
    error: str = ""
    #: The request was delivered whole; the server may have processed it. False
    #: only when the failure happened during connect or send. Decides repeats.
    sent: bool = True

    @property
    def ok(self) -> bool:
        return self.status == OK

    @property
    def charset(self) -> str:
        content_type = ""
        for key, value in self.headers.items():
            if key.lower() == "content-type":
                content_type = value
                break
        for part in content_type.split(";")[1:]:
            name, _, value = part.strip().partition("=")
            if name.strip().lower() == "charset" and value:
                return value.strip().strip('"').lower()
        return "utf-8"


class Transport(Protocol):
    def send(
        self, path: str, body: dict[str, Any], *, timeout: float
    ) -> TransportResult: ...
