from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FileListing:
    """Result of :meth:`DocProvider.list_files`.

    Carries the file paths plus whether the listing was *complete*. GitHub's
    recursive tree endpoint silently caps huge trees (HTTP 200 with a partial
    list and ``"truncated": true``); a provider sets ``truncated`` so the
    scanner can mark the repo result incomplete instead of scanning it as if
    clean.
    """

    paths: list[str] = field(default_factory=list)
    truncated: bool = False
    truncated_reason: str | None = None


class RepositoryDiscoveryProvider(Protocol):
    """Minimal provider contract required to discover eligible repositories."""

    def list_repos(self, org: str) -> list[str]:
        """Return list of repositories (full_name) belonging to an organization."""
        ...

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        """Return True if the given path exists in the repo at the given branch."""
        ...


class DocProvider(RepositoryDiscoveryProvider, Protocol):
    """Full provider contract required to scan repository content."""

    def list_files(self, repo: str, branch: str) -> FileListing:
        """Return the RST file paths in the repo plus a truncation flag."""
        ...

    def fetch_content(self, repo: str, path: str, branch: str) -> str:
        """Return the textual content of a file in the repo at the given branch."""
        ...

    def get_commit_hash(self, repo: str, branch: str) -> str | None:
        """Return the head commit SHA of `branch`, or None if unavailable."""
        ...
