"""Resumable repository discovery independent of scanning and parsing."""

from __future__ import annotations

from collections.abc import Set
from dataclasses import dataclass

from tools.scanner.eligibility import (
    check_repository_eligibility,
    interruption_from_repository_error,
)
from tools.scanner.interfaces import RepositoryDiscoveryProvider
from tools.shared.exceptions import ProviderError
from tools.shared.repository import RepositoryInterruption


@dataclass(frozen=True)
class DiscoveredRepository:
    """Eligibility recorded by one successful path lookup."""

    repo: str
    has_api_ref: bool


@dataclass(frozen=True)
class DiscoveryResult:
    """Completed checks plus an optional reason discovery stopped."""

    repositories: list[DiscoveredRepository]
    interruption: RepositoryInterruption | None


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
    except ProviderError as exc:
        return DiscoveryResult([], interruption_from_repository_error(exc, repo=None))

    discovered: list[DiscoveredRepository] = []
    seen: set[str] = set()

    for repo in repos:
        if repo in seen:
            continue
        seen.add(repo)
        if repo in skip_repos:
            continue

        eligibility = check_repository_eligibility(
            provider,
            repo=repo,
            ref=branch,
            api_ref_path=api_ref_path,
        )
        if eligibility.interruption is not None:
            return DiscoveryResult(discovered, eligibility.interruption)

        assert eligibility.has_api_ref is not None
        discovered.append(
            DiscoveredRepository(repo=repo, has_api_ref=eligibility.has_api_ref)
        )

    return DiscoveryResult(discovered, interruption=None)
