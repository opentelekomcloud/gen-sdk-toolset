"""Public contracts that describe one scanner session."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .document import DocumentScanResult
from .issue import Issue, IssueCode
from .section import SectionScanResult, SectionStatus

if TYPE_CHECKING:
    from .repository import (
        RepositoryInterruption,
        RepositoryInterruptionKind,
        RepositoryScanResult,
    )

__all__ = [
    "DocumentScanResult",
    "Issue",
    "IssueCode",
    "RepositoryInterruption",
    "RepositoryInterruptionKind",
    "RepositoryScanResult",
    "SectionScanResult",
    "SectionStatus",
]

_REPOSITORY_EXPORTS = {
    "RepositoryInterruption",
    "RepositoryInterruptionKind",
    "RepositoryScanResult",
}


def __getattr__(name: str) -> Any:
    if name not in _REPOSITORY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from . import repository

    value = getattr(repository, name)
    globals()[name] = value
    return value
