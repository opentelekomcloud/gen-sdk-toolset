"""GitHub client behaviours.

* S2 (#24): HTTP status → domain-exception mapping.
* S1 (#23): waiting out rate limits and running to completion — driven through
  the public API with a stub transport, so no real HTTP or sleeping happens.
"""

from __future__ import annotations

import time

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


def _provider(session: _Session, *, max_retries: int = 3) -> GitHubDocProvider:
    provider = GitHubDocProvider(
        token="t",
        api_url="https://api",
        prefix="p/",
        max_rate_limit_retries=max_retries,
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
# Rate-limit resilience (S1)
# --------------------------------------------------------------------------- #
def test_waits_out_a_single_rate_limit_and_completes(monkeypatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)  # record the wait, don't block

    reset = int(time.time()) + 30
    session = _Session(
        [_rate_limited(reset), _Resp(200, json_data=[{"full_name": "o/a"}])]
    )
    provider = _provider(session)

    repos = provider.list_repos("o")

    assert repos == ["o/a"]  # the call ran to completion despite the limit
    assert session.calls == 2  # rate-limited once, then retried successfully
    # Waited ~ until the reset (plus a small clock-skew buffer), not longer.
    assert len(slept) == 1
    assert 28 <= slept[0] <= 34


def test_gives_up_after_max_retries(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    reset = int(time.time()) + 1
    session = _Session([_rate_limited(reset) for _ in range(3)])
    provider = _provider(session, max_retries=2)

    with pytest.raises(RateLimitError):
        provider.list_repos("o")

    assert session.calls == 3  # initial attempt + 2 retries


def test_seconds_until_reset_is_bounded_and_nonnegative() -> None:
    # Past reset -> clamped to 0; absurd future -> capped; missing -> buffer.
    assert GitHubDocProvider._seconds_until_reset(int(time.time()) - 100) == 0
    assert GitHubDocProvider._seconds_until_reset(int(time.time()) + 10**9) <= 3600
    assert GitHubDocProvider._seconds_until_reset(None) == 2
