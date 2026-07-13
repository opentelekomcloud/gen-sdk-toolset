"""GitHub client behaviours.

* S2 (#24): HTTP status → domain-exception mapping.
* S1 (#23): rate limits are reported immediately without provider-level retry.
"""

from __future__ import annotations

import pytest

from tools.scanner.github.client import GitHubDocProvider
from tools.shared.exceptions import NotFoundError, RateLimitError


class _Resp:
    def __init__(
        self, status_code: int, *, headers: dict | None = None, json_data=None
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data
        self.text = ""

    def json(self):
        return self._json


class _Session:
    """Returns queued responses; records how many GETs were made."""

    def __init__(self, responses: list[_Resp]):
        self._responses = list(responses)
        self.headers: dict[str, str] = {}
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return self._responses.pop(0)


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
    provider.session = session  # swap in the stub transport
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
