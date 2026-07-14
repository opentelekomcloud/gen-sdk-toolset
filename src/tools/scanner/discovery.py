"""Cheap repository discovery independent of scanning and parsing."""

from __future__ import annotations

import logging

from tools.scanner.interfaces import RepositoryDiscoveryProvider
from tools.shared.exceptions import (
    AuthenticationError,
    RateLimitError,
    RepositoryError,
)

logger = logging.getLogger(__name__)


def discover_eligible_repos(
    provider: RepositoryDiscoveryProvider,
    *,
    org: str,
    api_ref_path: str,
    branch: str = "main",
) -> list[str]:
    """Return repositories containing ``api_ref_path`` at ``branch``.

    Repository-local lookup failures are skipped. Authentication and rate-limit
    failures invalidate the whole result and therefore propagate immediately.
    The result is additive discovery output, not an authoritative absence list:
    callers must not delete repositories merely because they are omitted.
    """
    repos = provider.list_repos(org)
    eligible: list[str] = []
    seen: set[str] = set()

    for repo in repos:
        if repo in seen:
            continue
        seen.add(repo)

        try:
            path_exists = provider.path_exists(repo, branch, api_ref_path)
        except RateLimitError:
            raise
        except AuthenticationError:
            raise
        except RepositoryError as exc:
            logger.warning(
                "Skipping %s during discovery: could not check %s at %s: %s",
                repo,
                api_ref_path,
                branch,
                exc,
            )
            continue

        if path_exists:
            eligible.append(repo)

    return eligible
