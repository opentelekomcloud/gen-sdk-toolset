"""GitHub client behaviours.

* S2 (#24): HTTP status -> domain-exception mapping.
* S1 (#23): rate limits are reported immediately without provider-level retry.
"""

from __future__ import annotations

import pytest
import requests

from tools.scanner.github.client import GitHubDocProvider
from tools.shared.exceptions import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RepositoryError,
)


class _Resp:
    def __init__(
        self,
        status_code: int,
        *,
        headers: dict | None = None,
        json_data=None,
        text: str = "",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class _Session:
    """Returns queued outcomes and records GET calls."""

    def __init__(self, responses: list[_Resp | Exception]):
        self._responses = list(responses)
        self.headers: dict[str, str] = {}
        self.calls = 0
        self.requests: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.calls += 1
        self.requests.append((url, kwargs))
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _rate_limited(reset: int) -> _Resp:
    return _Resp(
        403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)},
    )


def _provider(session: _Session) -> GitHubDocProvider:
    provider = GitHubDocProvider(
        token="t",
        api_url="https://api",
        prefix="p/",
    )
    provider.session = session
    return provider


# --------------------------------------------------------------------------- #
# Status mapping (S2)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", [404, 409])
def test_missing_or_empty_repo_maps_to_not_found(status: int) -> None:
    # 404 = missing; 409 = empty repository (no commits/tree yet). Both should
    # surface as NotFoundError so callers treat them as "nothing to scan".
    with pytest.raises(NotFoundError):
        GitHubDocProvider._raise_for_status(
            _Resp(status), repo="o/r", resource="commits"
        )


# --------------------------------------------------------------------------- #
# Rate-limit reporting (S1)
# --------------------------------------------------------------------------- #
def test_rate_limit_is_raised_immediately_without_retry() -> None:
    reset = 1_800_000_000
    session = _Session([_rate_limited(reset)])
    provider = _provider(session)

    with pytest.raises(RateLimitError) as exc_info:
        provider.list_repos("o")

    assert exc_info.value.reset_time == reset
    assert session.calls == 1


def test_list_repos_paginates_and_omits_archived_repositories() -> None:
    first_page = [
        {"full_name": f"o/repo-{index}", "archived": index == 0} for index in range(100)
    ]
    second_page = [
        {"full_name": "o/active", "archived": False},
        {"full_name": "o/archived", "archived": True},
    ]
    session = _Session(
        [_Resp(200, json_data=first_page), _Resp(200, json_data=second_page)]
    )

    repos = _provider(session).list_repos("o")

    assert "o/repo-0" not in repos
    assert "o/repo-1" in repos
    assert "o/active" in repos
    assert "o/archived" not in repos
    assert [request[1]["params"]["page"] for request in session.requests] == [1, 2]


def test_path_exists_forwards_branch_as_ref() -> None:
    session = _Session([_Resp(200, json_data={})])

    assert _provider(session).path_exists("o/r", "stable", "api-ref/source")
    assert session.requests[0] == (
        "https://api/repos/o/r/contents/api-ref/source",
        {"timeout": 30, "params": {"ref": "stable"}},
    )


@pytest.mark.parametrize("status", [404, 409])
def test_path_exists_converts_not_found_to_false(status: int) -> None:
    assert _provider(_Session([_Resp(status)])).path_exists("o/r", "main", "p") is False


@pytest.mark.parametrize(
    ("response", "expected_error"),
    [
        (_Resp(401), AuthenticationError),
        (_rate_limited(1_800_000_000), RateLimitError),
        (_Resp(403), PermissionDeniedError),
        (_Resp(500, text="server failed"), RepositoryError),
    ],
)
def test_path_exists_preserves_operational_errors(
    response: _Resp,
    expected_error: type[RepositoryError],
) -> None:
    with pytest.raises(expected_error):
        _provider(_Session([response])).path_exists("o/r", "main", "p")


def test_path_exists_wraps_transport_errors_instead_of_returning_false() -> None:
    provider = _provider(_Session([requests.ConnectionError("offline")]))

    with pytest.raises(RepositoryError, match="offline") as exc_info:
        provider.path_exists("o/r", "main", "p")

    assert isinstance(exc_info.value.cause, requests.ConnectionError)
