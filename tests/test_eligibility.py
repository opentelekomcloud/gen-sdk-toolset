from __future__ import annotations

import pytest

from tools.scanner.eligibility import EligibilityResult, check_repository_eligibility
from tools.shared.exceptions import ProviderError, ProviderErrorKind
from tools.shared.scan import RepositoryInterruptionKind


class _PathProvider:
    def __init__(self, outcome: bool | ProviderError) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, str, str]] = []

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        self.calls.append((repo, branch, path))
        if isinstance(self.outcome, ProviderError):
            raise self.outcome
        return self.outcome


@pytest.mark.parametrize("has_api_ref", [True, False])
def test_check_returns_completed_eligibility(has_api_ref: bool) -> None:
    provider = _PathProvider(has_api_ref)

    result = check_repository_eligibility(
        provider,
        repo="o/r",
        ref="a" * 40,
        api_ref_path="api-ref/source",
    )

    assert result == EligibilityResult(has_api_ref=has_api_ref)
    assert provider.calls == [("o/r", "a" * 40, "api-ref/source")]


def test_check_returns_typed_interruption_without_raising() -> None:
    provider = _PathProvider(
        ProviderError(
            "rate limited",
            kind=ProviderErrorKind.rate_limit,
            reset_time=1_800_000_000,
        )
    )

    result = check_repository_eligibility(
        provider,
        repo="o/r",
        ref="main",
        api_ref_path="p",
    )

    assert result.has_api_ref is None
    assert result.interruption is not None
    assert result.interruption.kind is RepositoryInterruptionKind.rate_limit
    assert result.interruption.repository == "o/r"
    assert result.interruption.reset_time == 1_800_000_000


@pytest.mark.parametrize(
    ("has_api_ref", "has_interruption"),
    [(None, False), (True, True)],
)
def test_result_rejects_ambiguous_states(
    has_api_ref: bool | None,
    has_interruption: bool,
) -> None:
    interruption = check_repository_eligibility(
        _PathProvider(
            ProviderError("failed", kind=ProviderErrorKind.unexpected_response)
        ),
        repo="o/r",
        ref="main",
        api_ref_path="p",
    ).interruption

    with pytest.raises(ValueError, match="either has_api_ref or interruption"):
        EligibilityResult(
            has_api_ref=has_api_ref,
            interruption=interruption if has_interruption else None,
        )
