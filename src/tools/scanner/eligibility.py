"""Shared repository eligibility check used by discovery and scanning."""

from __future__ import annotations

from dataclasses import dataclass

from tools.scanner.interfaces import RepositoryEligibilityProvider
from tools.shared.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
    RepositoryError,
)
from tools.shared.repository import (
    RepositoryInterruption,
    RepositoryInterruptionKind,
)


@dataclass(frozen=True)
class EligibilityResult:
    """One completed eligibility check or its typed interruption."""

    has_api_ref: bool | None
    interruption: RepositoryInterruption | None = None

    def __post_init__(self) -> None:
        has_result = self.has_api_ref is not None
        has_interruption = self.interruption is not None
        if has_result == has_interruption:
            raise ValueError(
                "EligibilityResult requires either has_api_ref or interruption"
            )


def check_repository_eligibility(
    provider: RepositoryEligibilityProvider,
    *,
    repo: str,
    ref: str,
    api_ref_path: str,
) -> EligibilityResult:
    """Check ``api_ref_path`` once and convert repository errors into data."""
    try:
        has_api_ref = provider.path_exists(repo, ref, api_ref_path)
    except RepositoryError as exc:
        return EligibilityResult(
            has_api_ref=None,
            interruption=interruption_from_repository_error(exc, repo=repo),
        )
    return EligibilityResult(has_api_ref=has_api_ref)


def interruption_from_repository_error(
    error: RepositoryError,
    *,
    repo: str | None,
) -> RepositoryInterruption:
    """Convert a repository exception into a serializable typed value."""
    reset_time: int | None = None
    if isinstance(error, RateLimitError):
        kind = RepositoryInterruptionKind.rate_limit
        if error.reset_time is not None and error.reset_time > 0:
            reset_time = error.reset_time
    elif isinstance(error, AuthenticationError):
        kind = RepositoryInterruptionKind.authentication
    elif isinstance(error, PermissionDeniedError):
        kind = RepositoryInterruptionKind.permission_denied
    else:
        kind = RepositoryInterruptionKind.repository_failure

    return RepositoryInterruption(
        kind=kind,
        repository=repo,
        message=str(error),
        reset_time=reset_time,
    )
