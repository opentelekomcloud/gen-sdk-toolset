"""S2 (#24): HTTP status → domain-exception mapping in the GitHub client."""

from __future__ import annotations

import pytest

from tools.scanner.github.client import GitHubDocProvider
from tools.shared.exceptions import NotFoundError


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.text = ""


@pytest.mark.parametrize("status", [404, 409])
def test_missing_or_empty_repo_maps_to_not_found(status: int) -> None:
    # 404 = missing; 409 = empty repository (no commits/tree yet). Both should
    # surface as NotFoundError so callers treat them as "nothing to scan".
    with pytest.raises(NotFoundError):
        GitHubDocProvider._raise_for_status(
            _Resp(status), repo="o/r", resource="commits"
        )
