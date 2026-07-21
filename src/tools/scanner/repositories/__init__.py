"""Repository discovery and scan eligibility."""

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
    "check_repository_eligibility",
    "discover_repositories",
]
