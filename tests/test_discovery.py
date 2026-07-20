from __future__ import annotations

from collections.abc import Set

import pytest

from tools.scanner.discovery import DiscoveredRepository, discover_repositories
from tools.shared.exceptions import ProviderError, ProviderErrorKind
from tools.shared.scan import RepositoryInterruptionKind


class _Provider:
    """Strict fake exposing only the discovery port."""

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
        if self.list_error:
            raise self.list_error
        return self.repos

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        self.path_calls.append((repo, branch, path))
        if error := self.path_errors.get(repo):
            raise error
        return repo in self.eligible


def _discover(provider: _Provider, **kwargs):
    return discover_repositories(provider, org="o", api_ref_path="p", **kwargs)


def test_returns_both_states_in_stable_order_and_forwards_arguments() -> None:
    provider = _Provider(["o/b", "o/a", "o/b", "o/c"], eligible={"o/b", "o/c"})

    result = _discover(provider, branch="stable")

    assert result.repositories == [
        DiscoveredRepository("o/b", True),
        DiscoveredRepository("o/a", False),
        DiscoveredRepository("o/c", True),
    ]
    assert result.interruption is None
    assert provider.list_calls == ["o"]
    assert provider.path_calls == [
        ("o/b", "stable", "p"),
        ("o/a", "stable", "p"),
        ("o/c", "stable", "p"),
    ]


def test_empty_organization_returns_empty_complete_result() -> None:
    result = _discover(_Provider([]))
    assert result.repositories == []
    assert result.interruption is None


def test_skipped_repositories_are_not_checked_or_returned() -> None:
    provider = _Provider(["o/a", "o/b", "o/a", "o/c"], eligible={"o/c"})

    result = _discover(provider, skip_repos={"o/a", "o/b"})

    assert result.repositories == [DiscoveredRepository("o/c", True)]
    assert provider.path_calls == [("o/c", "main", "p")]


def test_repository_failure_returns_checked_prefix_and_stops() -> None:
    provider = _Provider(
        ["o/a", "o/b", "o/broken", "o/later"],
        eligible={"o/a"},
        path_errors={
            "o/broken": ProviderError(
                "lookup failed", kind=ProviderErrorKind.unexpected_response
            )
        },
    )

    result = _discover(provider)

    assert result.repositories == [
        DiscoveredRepository("o/a", True),
        DiscoveredRepository("o/b", False),
    ]
    assert result.interruption is not None
    assert result.interruption.kind is RepositoryInterruptionKind.repository_failure
    assert result.interruption.repository == "o/broken"
    assert result.interruption.message == "lookup failed"
    assert [call[0] for call in provider.path_calls] == ["o/a", "o/b", "o/broken"]


def test_rate_limit_returns_prefix_context_and_reset_time() -> None:
    provider = _Provider(
        ["o/first", "o/limited", "o/later"],
        eligible={"o/first"},
        path_errors={
            "o/limited": ProviderError(
                "rate limited",
                kind=ProviderErrorKind.rate_limit,
                reset_time=1_800_000_000,
            )
        },
    )

    result = _discover(provider)

    assert result.repositories == [DiscoveredRepository("o/first", True)]
    assert result.interruption is not None
    assert result.interruption.kind is RepositoryInterruptionKind.rate_limit
    assert result.interruption.repository == "o/limited"
    assert result.interruption.reset_time == 1_800_000_000
    assert [call[0] for call in provider.path_calls] == ["o/first", "o/limited"]


@pytest.mark.parametrize("reset_time", [None, 0, -1])
def test_rate_limit_discards_unusable_reset_time(reset_time: int | None) -> None:
    result = _discover(
        _Provider(
            ["o/r"],
            path_errors={
                "o/r": ProviderError(
                    "rate limited",
                    kind=ProviderErrorKind.rate_limit,
                    reset_time=reset_time,
                )
            },
        )
    )
    assert result.interruption is not None
    assert result.interruption.reset_time is None


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (
            ProviderError("bad token", kind=ProviderErrorKind.authentication),
            RepositoryInterruptionKind.authentication,
        ),
        (
            ProviderError("forbidden", kind=ProviderErrorKind.permission_denied),
            RepositoryInterruptionKind.permission_denied,
        ),
    ],
)
def test_access_failures_remain_distinguishable(
    error: ProviderError, kind: RepositoryInterruptionKind
) -> None:
    result = _discover(_Provider(["o/r"], path_errors={"o/r": error}))
    assert result.interruption is not None
    assert result.interruption.kind is kind


def test_listing_failure_returns_empty_interrupted_result() -> None:
    result = _discover(
        _Provider(
            [],
            list_error=ProviderError(
                "listing failed", kind=ProviderErrorKind.unexpected_response
            ),
        )
    )
    assert result.repositories == []
    assert result.interruption is not None
    assert result.interruption.kind is RepositoryInterruptionKind.repository_failure
    assert result.interruption.repository is None


@pytest.mark.parametrize("stage", ["list", "path"])
def test_unexpected_exception_propagates(stage: str) -> None:
    error = RuntimeError("bug")
    provider = _Provider(
        ["o/r"],
        list_error=error if stage == "list" else None,
        path_errors={"o/r": error} if stage == "path" else None,
    )
    with pytest.raises(RuntimeError, match="bug"):
        _discover(provider)


def test_fake_has_no_scanning_operations() -> None:
    provider = _Provider([])
    assert not hasattr(provider, "get_commit_hash")
    assert not hasattr(provider, "list_files")
    assert not hasattr(provider, "fetch_content")
