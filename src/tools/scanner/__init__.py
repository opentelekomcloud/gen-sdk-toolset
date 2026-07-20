"""Scanner entrypoints."""

from tools.shared.scan import (
    RepositoryInterruption,
    RepositoryInterruptionKind,
)

from .discovery import (
    DiscoveredRepository,
    DiscoveryResult,
    discover_repositories,
)
from .eligibility import EligibilityResult, check_repository_eligibility

__all__ = [
    "DiscoveredRepository",
    "DiscoveryResult",
    "EligibilityResult",
    "RepositoryInterruption",
    "RepositoryInterruptionKind",
    "check_repository_eligibility",
    "discover_repositories",
]
