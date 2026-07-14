"""Resumable repository discovery independent of scanning and parsing."""

from __future__ import annotations

import enum
from collections.abc import Set
from dataclasses import dataclass

from tools.scanner.interfaces import RepositoryDiscoveryProvider
from tools.shared.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
    RepositoryError,
)


class DiscoveryInterruptionKind(str, enum.Enum):
    """Operational reasons why discovery stopped before completion."""

    rate_limit = "rate_limit"
    authentication = "authentication"
    permission_denied = "permission_denied"
    repository_failure = "repository_failure"


@dataclass(frozen=True)
class DiscoveryInterruption:
    """Typed operational failure returned with a checked repository prefix."""

    kind: DiscoveryInterruptionKind
    repository: str | None
    message: str
    reset_time: int | None = None


@dataclass(frozen=True)
class DiscoveredRepository:
    """Eligibility recorded by one successful path lookup."""

    repo: str
    has_api_ref: bool


@dataclass(frozen=True)
class DiscoveryResult:
    """Completed checks plus an optional reason discovery stopped."""

    repositories: list[DiscoveredRepository]
    interruption: DiscoveryInterruption | None


def discover_repositories(
    provider: RepositoryDiscoveryProvider,
    *,
    org: str,
    api_ref_path: str,
    branch: str = "main",
    skip_repos: Set[str] = frozenset(),
) -> DiscoveryResult:
    """Check repository eligibility until complete or operationally interrupted."""
    try:
        repos = provider.list_repos(org)
    except RepositoryError as exc:
        return DiscoveryResult([], _map_interruption(exc, repository=None))

    discovered: list[DiscoveredRepository] = []
    seen: set[str] = set()

    for repo in repos:
        if repo in seen:
            continue
        seen.add(repo)
        if repo in skip_repos:
            continue

        try:
            has_api_ref = provider.path_exists(repo, branch, api_ref_path)
        except RepositoryError as exc:
            return DiscoveryResult(
                discovered,
                _map_interruption(exc, repository=repo),
            )

        discovered.append(DiscoveredRepository(repo=repo, has_api_ref=has_api_ref))

    return DiscoveryResult(discovered, interruption=None)


def _map_interruption(
    error: RepositoryError,
    *,
    repository: str | None,
) -> DiscoveryInterruption:
    reset_time: int | None = None
    if isinstance(error, RateLimitError):
        kind = DiscoveryInterruptionKind.rate_limit
        if error.reset_time is not None and error.reset_time > 0:
            reset_time = error.reset_time
    elif isinstance(error, AuthenticationError):
        kind = DiscoveryInterruptionKind.authentication
    elif isinstance(error, PermissionDeniedError):
        kind = DiscoveryInterruptionKind.permission_denied
    else:
        kind = DiscoveryInterruptionKind.repository_failure

    return DiscoveryInterruption(
        kind=kind,
        repository=repository,
        message=str(error),
        reset_time=reset_time,
    )
