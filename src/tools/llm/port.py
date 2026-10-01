"""The LLM contract: ``complete(Request) -> Result``.

Expected model, network and response failures come back as
``Result(ok=False, failure=...)`` rather than as exceptions, so a caller records
them instead of losing them in a log line. This module imports nothing from the
implementations behind it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

#: Every value ``Result.failure`` takes; ``""`` means success.
FAILURES = (
    "config",
    "rate_limit",
    "timeout",
    "network",
    "http",
    "empty",
    "truncated",
    "invalid_json",
    "schema_invalid",
)


@dataclass(frozen=True)
class Request:
    model: str
    system: str
    user: str
    purpose: str
    #: ``None``: raw text, nothing is parsed.
    schema_id: str | None = None
    #: How strictly the provider must honour the schema.
    schema_strict: bool = True
    max_tokens: int = 16000
    #: ``None``: the provider's default.
    temperature: float | None = None
    seed: int | None = None


@dataclass(frozen=True)
class Result:
    ok: bool
    text: str = ""
    data: dict[str, Any] | None = None
    failure: str = ""
    error: str = ""

    model: str = ""
    route: str = ""
    purpose: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    #: As the provider reported it; ``"length"`` means cut at ``max_tokens``.
    finish_reason: str = ""
    #: ``False``: the request never reached the provider. It cost nothing and says
    #: nothing about the model (DNS, a refused connection, a pause the limiter
    #: would not sit through, a config failure).
    sent: bool = True
    #: The provider's status code; ``0`` - no response at all. On ``http``
    #: failures a 4xx means the request itself was refused (key, quota, payload)
    #: and the model was never asked.
    http_status: int = 0

    ms: int = 0
    schema_sha: str = ""
    requested_at: str = ""


class LLM(Protocol):
    def complete(self, request: Request) -> Result: ...
