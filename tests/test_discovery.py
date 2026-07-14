from __future__ import annotations

from collections.abc import Set

import pytest

from tools.scanner.discovery import (
    DiscoveredRepository,
    DiscoveryInterruptionKind,
    DiscoveryResult,
    discover_repositories,
)
from tools.shared.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
    RepositoryError,
)


class _StrictProvider:
    """Discovery fake exposing only the two allowed provider operations."""

    def __init__(
        self,
        repos: list[str],
        *,
        eligible: Set[str] = frozenset(),
        path_errors: dict[str, Exception] | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self.repos = repos
        self.eligible = eligible
        self.path_errors = path_errors or {}
        self.list_error = list_error
        self.list_calls: list[str] = []
        self.path_calls: list[tuple[str, str, str]] = []

    def list_repos(self, org: str) -> list[str]:
        self.list_calls.append(org)
        if self.list_error is not None:
            raise self.list_error
        return self.repos

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        self.path_calls.append((repo, branch, path))
        if error := self.path_errors.get(repo):
            raise error
        return repo in self.eligible


def test_returns_both_eligibility_states_in_stable_provider_order() -> None:
    provider = _StrictProvider(
        ["o/b", "o/a", "o/b", "o/c"],
        eligible={"o/b", "o/c"},
    )

    result = discover_repositories(
        provider,
        org="o",
        branch="stable",
        api_ref_path="api-ref/source",
    )

    assert result == DiscoveryResult(
        repositories=[
            DiscoveredRepository(repo="o/b", has_api_ref=True),
            DiscoveredRepository(repo="o/a", has_api_ref=False),
            DiscoveredRepository(repo="o/c", has_api_ref=True),
        ],
        interruption=None,
    )
    assert provider.list_calls == ["o"]
    assert provider.path_calls == [
        ("o/b", "stable", "api-ref/source"),
        ("o/a", "stable", "api-ref/source"),
        ("o/c", "stable", "api-ref/source"),
    ]


def test_empty_organization_returns_empty_complete_result() -> None:
    provider = _StrictProvider([])

    result = discover_repositories(provider, org="o", api_ref_path="api-ref/source")

    assert result == DiscoveryResult(repositories=[], interruption=None)
    assert provider.list_calls == ["o"]
    assert provider.path_calls == []


def test_skip_repos_are_neither_checked_nor_returned() -> None:
    provider = _StrictProvider(["o/a", "o/b", "o/a", "o/c"], eligible={"o/c"})

    result = discover_repositories(
        provider,
        org="o",
        api_ref_path="api-ref/source",
        skip_repos={"o/a", "o/b"},
    )

    assert result.repositories == [DiscoveredRepository(repo="o/c", has_api_ref=True)]
    assert result.interruption is None
    assert provider.path_calls == [("o/c", "main", "api-ref/source")]


def test_repository_failure_returns_checked_prefix_and_stops() -> None:
    provider = _StrictProvider(
        ["o/a", "o/b", "o/broken", "o/not-checked"],
        eligible={"o/a"},
        path_errors={"o/broken": RepositoryError("lookup failed")},
    )

    result = discover_repositories(provider, org="o", api_ref_path="p")

    assert result.repositories == [
        DiscoveredRepository(repo="o/a", has_api_ref=True),
        DiscoveredRepository(repo="o/b", has_api_ref=False),
    ]
    assert result.interruption is not None
    assert result.interruption.kind is DiscoveryInterruptionKind.repository_failure
    assert result.interruption.repository == "o/broken"
    assert result.interruption.message == "lookup failed"
    assert result.interruption.reset_time is None
    assert provider.path_calls == [
        ("o/a", "main", "p"),
        ("o/b", "main", "p"),
        ("o/broken", "main", "p"),
    ]


def test_rate_limit_returns_prefix_repository_and_reset_time() -> None:
    provider = _StrictProvider(
        ["o/first", "o/limited", "o/not-checked"],
        eligible={"o/first"},
        path_errors={"o/limited": RateLimitError(reset_time=1_800_000_000)},
    )

    result = discover_repositories(provider, org="o", api_ref_path="p")

    assert result.repositories == [
        DiscoveredRepository(repo="o/first", has_api_ref=True)
    ]
    assert result.interruption is not None
    assert result.interruption.kind is DiscoveryInterruptionKind.rate_limit
    assert result.interruption.repository == "o/limited"
    assert result.interruption.reset_time == 1_800_000_000
    assert provider.path_calls == [
        ("o/first", "main", "p"),
        ("o/limited", "main", "p"),
    ]


@pytest.mark.parametrize("reset_time", [None, 0, -1])
def test_rate_limit_discards_unusable_reset_time(reset_time: int | None) -> None:
    provider = _StrictProvider(
        ["o/limited"],
        path_errors={"o/limited": RateLimitError(reset_time=reset_time)},
    )

    result = discover_repositories(provider, org="o", api_ref_path="p")

    assert result.interruption is not None
    assert result.interruption.reset_time is None


@pytest.mark.parametrize(
    ("error", "expected_kind"),
    [
        (
            AuthenticationError("invalid token"),
            DiscoveryInterruptionKind.authentication,
        ),
        (
            PermissionDeniedError("forbidden"),
            DiscoveryInterruptionKind.permission_denied,
        ),
    ],
)
def test_typed_access_failure_remains_distinguishable(
    error: RepositoryError,
    expected_kind: DiscoveryInterruptionKind,
) -> None:
    provider = _StrictProvider(["o/private"], path_errors={"o/private": error})

    result = discover_repositories(provider, org="o", api_ref_path="p")

    assert result.repositories == []
    assert result.interruption is not None
    assert result.interruption.kind is expected_kind
    assert result.interruption.repository == "o/private"


@pytest.mark.parametrize(
    ("error", "expected_kind", "expected_reset"),
    [
        (
            RateLimitError(reset_time=1_800_000_000),
            DiscoveryInterruptionKind.rate_limit,
            1_800_000_000,
        ),
        (
            AuthenticationError("invalid token"),
            DiscoveryInterruptionKind.authentication,
            None,
        ),
        (
            PermissionDeniedError("forbidden"),
            DiscoveryInterruptionKind.permission_denied,
            None,
        ),
        (
            RepositoryError("listing failed"),
            DiscoveryInterruptionKind.repository_failure,
            None,
        ),
    ],
)
def test_listing_failure_returns_empty_typed_interruption(
    error: RepositoryError,
    expected_kind: DiscoveryInterruptionKind,
    expected_reset: int | None,
) -> None:
    provider = _StrictProvider([], list_error=error)

    result = discover_repositories(provider, org="o", api_ref_path="p")

    assert result.repositories == []
    assert result.interruption is not None
    assert result.interruption.kind is expected_kind
    assert result.interruption.repository is None
    assert result.interruption.reset_time == expected_reset
    assert provider.path_calls == []


@pytest.mark.parametrize("stage", ["list", "path"])
def test_unexpected_exception_propagates(stage: str) -> None:
    error = RuntimeError("bug")
    provider = _StrictProvider(
        ["o/a"],
        list_error=error if stage == "list" else None,
        path_errors={"o/a": error} if stage == "path" else None,
    )

    with pytest.raises(RuntimeError, match="bug"):
        discover_repositories(provider, org="o", api_ref_path="p")


def test_discovery_provider_does_not_expose_scanning_operations() -> None:
    provider = _StrictProvider([])

    assert not hasattr(provider, "get_commit_hash")
    assert not hasattr(provider, "list_files")
    assert not hasattr(provider, "fetch_content")
