from __future__ import annotations

import enum
from dataclasses import dataclass


class RepositoryInterruptionKind(str, enum.Enum):
    """Operational reasons why a repository operation stopped."""

    rate_limit = "rate_limit"
    authentication = "authentication"
    permission_denied = "permission_denied"
    repository_failure = "repository_failure"


@dataclass(frozen=True)
class RepositoryInterruption:
    """Typed repository failure safe to return across application layers."""

    kind: RepositoryInterruptionKind
    repository: str | None
    message: str
    reset_time: int | None = None
