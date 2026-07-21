"""Scanner entrypoints."""

from tools.shared.scan import (
    RepositoryInterruption,
    RepositoryInterruptionKind,
)

from .repositories import (
    DiscoveredRepository,
    DiscoveryResult,
    EligibilityResult,
    check_repository_eligibility,
    discover_repositories,
)

__all__ = [
    "DiscoveredRepository",
    "DiscoveryResult",
    "EligibilityResult",
    "RepositoryInterruption",
    "RepositoryInterruptionKind",
    "check_repository_eligibility",
    "discover_repositories",
]
