from __future__ import annotations

import logging

import pytest

from tools.scanner.discovery import discover_eligible_repos
from tools.shared.exceptions import (
    AuthenticationError,
    RateLimitError,
    RepositoryError,
)


class _StrictProvider:
    """Discovery fake exposing only the two allowed provider operations."""

    def __init__(
        self,
        repos: list[str],
        *,
        eligible: set[str] | None = None,
        path_errors: dict[str, RepositoryError] | None = None,
        list_error: RepositoryError | None = None,
    ) -> None:
        self.repos = repos
        self.eligible = eligible or set()
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


def test_discovers_in_provider_order_and_deduplicates() -> None:
    provider = _StrictProvider(
        ["o/b", "o/a", "o/b", "o/c"],
        eligible={"o/b", "o/c"},
    )

    result = discover_eligible_repos(
        provider,
        org="o",
        branch="stable",
        api_ref_path="api-ref/source",
    )

    assert result == ["o/b", "o/c"]
    assert provider.list_calls == ["o"]
    assert provider.path_calls == [
        ("o/b", "stable", "api-ref/source"),
        ("o/a", "stable", "api-ref/source"),
        ("o/c", "stable", "api-ref/source"),
    ]


def test_empty_organization_returns_empty_result() -> None:
    provider = _StrictProvider([])

    assert (
        discover_eligible_repos(provider, org="o", api_ref_path="api-ref/source") == []
    )
    assert provider.list_calls == ["o"]
    assert provider.path_calls == []


def test_repository_error_is_logged_and_only_that_repo_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = _StrictProvider(
        ["o/good", "o/broken", "o/also-good"],
        eligible={"o/good", "o/also-good"},
        path_errors={"o/broken": RepositoryError("lookup failed")},
    )

    with caplog.at_level(logging.WARNING, logger="tools.scanner.discovery"):
        result = discover_eligible_repos(
            provider,
            org="o",
            api_ref_path="api-ref/source",
        )

    assert result == ["o/good", "o/also-good"]
    assert "o/broken" in caplog.text
    assert "lookup failed" in caplog.text


def test_rate_limit_interrupts_and_stops_further_checks() -> None:
    error = RateLimitError(reset_time=1_800_000_000)
    provider = _StrictProvider(
        ["o/first", "o/limited", "o/not-checked"],
        eligible={"o/first", "o/not-checked"},
        path_errors={"o/limited": error},
    )

    with pytest.raises(RateLimitError) as exc_info:
        discover_eligible_repos(provider, org="o", api_ref_path="api-ref/source")

    assert exc_info.value is error
    assert provider.path_calls == [
        ("o/first", "main", "api-ref/source"),
        ("o/limited", "main", "api-ref/source"),
    ]


def test_authentication_error_interrupts_discovery() -> None:
    error = AuthenticationError("invalid token")
    provider = _StrictProvider(
        ["o/private", "o/not-checked"],
        path_errors={"o/private": error},
    )

    with pytest.raises(AuthenticationError) as exc_info:
        discover_eligible_repos(provider, org="o", api_ref_path="api-ref/source")

    assert exc_info.value is error
    assert provider.path_calls == [("o/private", "main", "api-ref/source")]


def test_organization_listing_error_propagates_without_path_checks() -> None:
    error = RepositoryError("organization listing failed")
    provider = _StrictProvider([], list_error=error)

    with pytest.raises(RepositoryError) as exc_info:
        discover_eligible_repos(provider, org="o", api_ref_path="api-ref/source")

    assert exc_info.value is error
    assert provider.path_calls == []
