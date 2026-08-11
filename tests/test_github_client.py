"""GitHub client behaviours.

* S2 (#24): HTTP status -> domain-exception mapping.
* S1 (#23): rate limits are reported immediately without provider-level retry.
"""

from __future__ import annotations

import base64

import pytest
import requests

from tools.scanner.github import client as client_module
from tools.scanner.github.client import GitHubDocProvider
from tools.shared.exceptions import ProviderError, ProviderErrorKind


class _Resp:
    def __init__(
        self,
        status_code: int,
        *,
        headers: dict | None = None,
        json_data=None,
        text: str = "",
        content: bytes | None = None,
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data
        self.text = text
        self.content = content if content is not None else text.encode()

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
    with pytest.raises(ProviderError) as exc_info:
        GitHubDocProvider._raise_for_status(
            _Resp(status), repo="o/r", resource="commits"
        )
    assert exc_info.value.kind is ProviderErrorKind.not_found


# --------------------------------------------------------------------------- #
# Rate-limit reporting (S1)
# --------------------------------------------------------------------------- #
def test_rate_limit_is_raised_immediately_without_retry() -> None:
    reset = 1_800_000_000
    session = _Session([_rate_limited(reset)])
    provider = _provider(session)

    with pytest.raises(ProviderError) as exc_info:
        provider.list_repos("o")

    assert exc_info.value.kind is ProviderErrorKind.rate_limit
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
    # Only public repositories are in scope for a docs scan.
    assert {request[1]["params"]["type"] for request in session.requests} == {"public"}


def _full_repo_page() -> list[dict]:
    """One page at the per_page limit, so the loop asks for another."""
    return [{"full_name": f"o/repo-{index}", "archived": False} for index in range(100)]


def test_list_repos_stops_on_an_empty_page() -> None:
    session = _Session(
        [_Resp(200, json_data=_full_repo_page()), _Resp(200, json_data=[])]
    )

    repos = _provider(session).list_repos("o")

    assert len(repos) == 100
    assert session.calls == 2


def test_list_repos_rejects_a_non_list_page() -> None:
    """A JSON object where the API documents an array is a provider fault, not
    the end of the inventory. Reading it as "no more pages" would return a
    truncated org listing under a clean status - every repository after the
    fault silently absent, with nothing downstream able to tell."""
    session = _Session(
        [
            _Resp(200, json_data=_full_repo_page()),
            _Resp(200, json_data={"message": "Not Found"}),
        ]
    )

    with pytest.raises(ProviderError) as exc_info:
        _provider(session).list_repos("o")

    assert exc_info.value.kind is ProviderErrorKind.unexpected_response


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
    ("response", "expected_kind"),
    [
        (_Resp(401), ProviderErrorKind.authentication),
        (_rate_limited(1_800_000_000), ProviderErrorKind.rate_limit),
        (_Resp(403), ProviderErrorKind.permission_denied),
        (_Resp(500, text="server failed"), ProviderErrorKind.unexpected_response),
    ],
)
def test_path_exists_preserves_operational_errors(
    response: _Resp,
    expected_kind: ProviderErrorKind,
) -> None:
    with pytest.raises(ProviderError) as exc_info:
        _provider(_Session([response])).path_exists("o/r", "main", "p")
    assert exc_info.value.kind is expected_kind


def test_path_exists_wraps_transport_errors_instead_of_returning_false() -> None:
    provider = _provider(_Session([requests.ConnectionError("offline")]))

    with pytest.raises(ProviderError, match="offline") as exc_info:
        provider.path_exists("o/r", "main", "p")

    assert exc_info.value.kind is ProviderErrorKind.connection_error
    assert isinstance(exc_info.value.cause, requests.ConnectionError)
    # The original transport failure also stays on the exception chain, so a
    # traceback shows what actually broke and not just the domain wrapper.
    assert exc_info.value.__cause__ is exc_info.value.cause


@pytest.mark.parametrize(
    "response",
    [
        _Resp(403, headers={"Retry-After": "60"}),
        _Resp(403, text="You have exceeded a secondary rate limit"),
        _Resp(429),
    ],
)
def test_secondary_rate_limits_remain_distinguishable_from_permission_denied(
    response: _Resp,
) -> None:
    with pytest.raises(ProviderError) as exc_info:
        _provider(_Session([response])).path_exists("o/r", "main", "p")
    assert exc_info.value.kind is ProviderErrorKind.rate_limit


def test_ordinary_403_mentioning_rate_limits_is_permission_denied() -> None:
    """A 403 body that mentions rate limits only in passing is a permission
    failure, and the kind is not cosmetic: `eligibility.py` turns it into a
    stored `RepositoryInterruptionKind`, so a broad body match files an access
    problem as a throttle - one that reads as "retry later" forever, since no
    amount of waiting grants the token access it was never given."""
    response = _Resp(
        403,
        text=(
            "Although you appear to have the correct authorization credentials,"
            " the organization has enabled OAuth App access restrictions."
            " See the rate limit documentation for details."
        ),
    )

    with pytest.raises(ProviderError) as exc_info:
        _provider(_Session([response])).path_exists("o/r", "main", "p")

    assert exc_info.value.kind is ProviderErrorKind.permission_denied


def test_unexpected_http_error_names_repository_and_resource() -> None:
    """An unexpected status is only actionable if the message says which
    repository and which resource produced it: during an org-wide scan a bare
    status and a wall of HTML identifies neither. The body stays capped so one
    server error page cannot bury the log it lands in."""
    session = _Session([_Resp(500, text="x" * 500)])

    with pytest.raises(ProviderError) as exc_info:
        _provider(session).path_exists("o/r", "main", "api-ref/source")

    message = str(exc_info.value)
    assert "o/r" in message
    assert "api-ref/source" in message
    assert message.endswith("x" * 200)
    assert "x" * 201 not in message


def test_every_request_uses_the_configured_timeout() -> None:
    """No GitHub call may hang indefinitely: a scan that never returns is
    indistinguishable from one that produced nothing."""
    session = _Session(
        [
            _Resp(200, json_data={"truncated": False, "tree": []}),
            _Resp(200, json_data=[{"sha": "abc"}]),
            _Resp(200, json_data={"type": "file", "encoding": "none"}),
            _Resp(200, content=b""),
        ]
    )
    provider = _provider(session)

    provider.list_files("o/r", "main")
    provider.get_commit_hash("o/r", "main")
    provider.fetch_content("o/r", "p/x.rst", "main")

    assert session.calls == 4
    assert [request[1]["timeout"] for request in session.requests] == [30] * 4


# --------------------------------------------------------------------------- #
# get_commit_hash
# --------------------------------------------------------------------------- #
def test_get_commit_hash_returns_the_head_sha_of_the_branch() -> None:
    session = _Session([_Resp(200, json_data=[{"sha": "deadbeef"}, {"sha": "older"}])])

    assert _provider(session).get_commit_hash("o/r", "stable") == "deadbeef"
    url, kwargs = session.requests[0]
    assert url == "https://api/repos/o/r/commits"
    # The branch is the `sha` filter, and one entry is all that is needed -
    # asking for more would carry a page of commits nobody reads.
    assert kwargs["params"] == {"sha": "stable", "per_page": 1}


@pytest.mark.parametrize(
    "response",
    [_Resp(200, json_data=[]), _Resp(404), _Resp(409)],
    ids=["empty-listing", "missing-repo", "empty-repo"],
)
def test_get_commit_hash_returns_none_when_the_ref_is_confirmed_absent(
    response: _Resp,
) -> None:
    """`None` is the provider's way of saying the ref is confirmed absent -
    the alternative would be inventing a SHA, or reading at the mutable branch
    name and calling the result a pinned snapshot. Only an empty listing or a
    status that says so earns it."""
    assert _provider(_Session([response])).get_commit_hash("o/r", "main") is None


@pytest.mark.parametrize(
    "payload",
    [{"message": "Git Repository is empty."}, [{"commit": {}}]],
    ids=["non-list-body", "entry-without-sha"],
)
def test_get_commit_hash_rejects_a_response_it_cannot_read(payload) -> None:
    """Neither of these is a ref confirmed absent, so neither may become None:
    the caller turns None into "commit SHA could not be resolved"
    (`service.py::_unresolved_commit_result`), which would report a provider
    fault as a repository that simply has no such branch."""
    with pytest.raises(ProviderError) as exc_info:
        _provider(_Session([_Resp(200, json_data=payload)])).get_commit_hash(
            "o/r", "main"
        )

    assert exc_info.value.kind is ProviderErrorKind.unexpected_response


@pytest.mark.parametrize(
    ("response", "expected_kind"),
    [
        (_Resp(401), ProviderErrorKind.authentication),
        (_rate_limited(1_800_000_000), ProviderErrorKind.rate_limit),
        (_Resp(403), ProviderErrorKind.permission_denied),
        (_Resp(500, text="server failed"), ProviderErrorKind.unexpected_response),
        (requests.ConnectionError("offline"), ProviderErrorKind.connection_error),
    ],
)
def test_get_commit_hash_preserves_operational_errors(
    response: _Resp | Exception,
    expected_kind: ProviderErrorKind,
) -> None:
    """Only `not_found` means "no such ref". Every other failure is one where
    we never got to look, and flattening it into None would report a branch as
    confirmed absent - `service.py::_unresolved_commit_result` would then log a
    missing ref where the real reason was an expired token or a rate limit."""
    with pytest.raises(ProviderError) as exc_info:
        _provider(_Session([response])).get_commit_hash("o/r", "main")
    assert exc_info.value.kind is expected_kind


# --------------------------------------------------------------------------- #
# fetch_content: base64 vs. raw-media-type fallback
# --------------------------------------------------------------------------- #
def test_fetch_content_returns_inline_base64_when_available() -> None:
    encoded = base64.b64encode(b"Example\n=======\n").decode()
    session = _Session(
        [
            _Resp(
                200,
                json_data={"type": "file", "encoding": "base64", "content": encoded},
            )
        ]
    )

    content = _provider(session).fetch_content("o/r", "p/x.rst", "main")

    assert content == "Example\n=======\n"
    assert session.calls == 1


def test_fetch_content_falls_back_to_raw_media_type_when_not_base64() -> None:
    session = _Session(
        [
            _Resp(200, json_data={"type": "file", "encoding": "none"}),
            _Resp(200, content=b"Example\n=======\n"),
        ]
    )

    content = _provider(session).fetch_content("o/r", "p/x.rst", "main")

    assert content == "Example\n=======\n"
    assert session.calls == 2
    assert session.requests[1][1]["headers"] == {
        "Accept": "application/vnd.github.raw+json"
    }


def test_fetch_content_raw_fallback_propagates_provider_error() -> None:
    session = _Session(
        [
            _Resp(200, json_data={"type": "file", "encoding": "none"}),
            _rate_limited(1_800_000_000),
        ]
    )

    with pytest.raises(ProviderError) as exc_info:
        _provider(session).fetch_content("o/r", "p/x.rst", "main")

    assert exc_info.value.kind is ProviderErrorKind.rate_limit


def test_fetch_content_raw_fallback_non_utf8_content_is_not_a_provider_error() -> None:
    """A bad-encoding large file is a document problem, not a transport one -
    it must raise plainly (like the base64 branch already does), not as a
    ProviderError, so ScannerService gates only this one document instead of
    failing the whole repository scan (see _fetch_document's except clauses)."""
    session = _Session(
        [
            _Resp(200, json_data={"type": "file", "encoding": "none"}),
            _Resp(200, content=b"\xff\xfe"),
        ]
    )

    with pytest.raises(UnicodeDecodeError):
        _provider(session).fetch_content("o/r", "p/x.rst", "main")


@pytest.mark.parametrize("entry_type", ["dir", "submodule", "symlink", None])
def test_fetch_content_rejects_anything_but_a_regular_file(entry_type) -> None:
    """Only a regular file has content to read. Anything else - an unresolved
    symlink, a submodule, a directory - is refused rather than run through the
    raw-media-type retry as if it were a large file."""
    session = _Session([_Resp(200, json_data={"type": entry_type, "encoding": "none"})])

    with pytest.raises(ProviderError) as exc_info:
        _provider(session).fetch_content("o/r", "p/x.rst", "main")

    assert exc_info.value.kind is ProviderErrorKind.unexpected_response
    assert session.calls == 1  # no raw retry was attempted


def test_fetch_content_rejects_an_unrecognized_encoding() -> None:
    """`none` specifically means "too large to inline", which the raw retry
    handles. Any other encoding is a shape this client does not understand,
    so it fails instead of retrying and hoping."""
    session = _Session([_Resp(200, json_data={"type": "file", "encoding": "utf-16"})])

    with pytest.raises(ProviderError) as exc_info:
        _provider(session).fetch_content("o/r", "p/x.rst", "main")

    assert exc_info.value.kind is ProviderErrorKind.unexpected_response
    assert session.calls == 1


# --------------------------------------------------------------------------- #
# list_files: truncated-tree directory-walk fallback
# --------------------------------------------------------------------------- #
def test_list_files_returns_paths_directly_when_tree_is_not_truncated() -> None:
    tree = [
        {"path": "p/a.rst", "type": "blob"},
        {"path": "p/b.txt", "type": "blob"},
        {"path": "other/c.rst", "type": "blob"},
    ]
    session = _Session([_Resp(200, json_data={"truncated": False, "tree": tree})])

    listing = _provider(session).list_files("o/r", "main")

    assert listing.paths == ["p/a.rst"]
    assert listing.truncated is False
    assert listing.truncated_reason is None
    assert session.calls == 1
    # A non-recursive tree would list only the repository root, so every path
    # under the prefix would silently vanish from the listing.
    assert session.requests[0][1]["params"]["recursive"] == "1"


def test_list_files_walks_prefix_when_tree_is_truncated() -> None:
    session = _Session(
        [
            _Resp(200, json_data={"truncated": True, "tree": []}),
            _Resp(  # directory listing of "p" (self.prefix stripped of "/")
                200,
                json_data=[
                    {"path": "p/a", "type": "dir"},
                    {"path": "p/x.rst", "type": "file"},
                    {"path": "p/readme.md", "type": "file"},
                ],
            ),
            _Resp(  # directory listing of "p/a"
                200,
                json_data=[{"path": "p/a/y.rst", "type": "file"}],
            ),
        ]
    )

    listing = _provider(session).list_files("o/r", "main")

    assert sorted(listing.paths) == ["p/a/y.rst", "p/x.rst"]
    assert listing.truncated is False
    assert listing.truncated_reason is None


def test_list_files_walk_reports_truncated_when_budget_exceeded(monkeypatch) -> None:
    monkeypatch.setattr(client_module, "_MAX_WALK_REQUESTS", 2)
    # Each directory yields exactly one more subdirectory, so the stack never
    # empties on its own - only the request budget stops the walk.
    session = _Session(
        [
            _Resp(200, json_data={"truncated": True, "tree": []}),
            _Resp(200, json_data=[{"path": "p/a", "type": "dir"}]),
            _Resp(200, json_data=[{"path": "p/a/b", "type": "dir"}]),
        ]
    )

    listing = _provider(session).list_files("o/r", "main")

    assert listing.paths == []
    assert listing.truncated is True
    assert "2 requests" in listing.truncated_reason
    assert session.calls == 3  # 1 tree call + the 2-request walk budget


def test_list_files_walk_aborts_on_genuine_provider_error() -> None:
    session = _Session(
        [
            _Resp(200, json_data={"truncated": True, "tree": []}),
            _rate_limited(1_800_000_000),
        ]
    )

    with pytest.raises(ProviderError) as exc_info:
        _provider(session).list_files("o/r", "main")

    assert exc_info.value.kind is ProviderErrorKind.rate_limit


def test_list_directory_rejects_non_list_response() -> None:
    session = _Session(
        [
            _Resp(200, json_data={"truncated": True, "tree": []}),
            _Resp(200, json_data={"encoding": "base64", "content": ""}),
        ]
    )

    with pytest.raises(ProviderError) as exc_info:
        _provider(session).list_files("o/r", "main")

    assert exc_info.value.kind is ProviderErrorKind.unexpected_response


def test_list_files_walk_includes_symlinked_rst_entries() -> None:
    """GitHub resolves an in-repo symlink to the file it points at, so a
    symlinked .rst is a readable document and must be counted - the git-tree
    path would have included it as a blob."""
    session = _Session(
        [
            _Resp(200, json_data={"truncated": True, "tree": []}),
            _Resp(
                200,
                json_data=[{"path": "p/linked.rst", "type": "symlink"}],
            ),
        ]
    )

    listing = _provider(session).list_files("o/r", "main")

    assert listing.paths == ["p/linked.rst"]
    assert listing.truncated is False


def test_list_files_walk_skips_submodules() -> None:
    """A submodule's content lives in another repository, so it is not part
    of this snapshot - skipped without being walked into or counted."""
    session = _Session(
        [
            _Resp(200, json_data={"truncated": True, "tree": []}),
            _Resp(
                200,
                json_data=[
                    {"path": "p/vendored", "type": "submodule"},
                    {"path": "p/vendored.rst", "type": "submodule"},
                    {"path": "p/real.rst", "type": "file"},
                ],
            ),
        ]
    )

    listing = _provider(session).list_files("o/r", "main")

    assert listing.paths == ["p/real.rst"]
    assert listing.truncated is False
    # The submodule was never listed as a directory.
    assert session.calls == 2


def test_list_files_walk_rejects_an_unknown_entry_type() -> None:
    """An .rst path of a type this walk does not understand means the listing
    cannot be classified, so it fails rather than guessing whether to read it."""
    session = _Session(
        [
            _Resp(200, json_data={"truncated": True, "tree": []}),
            _Resp(200, json_data=[{"path": "p/odd.rst", "type": "gitlink"}]),
        ]
    )

    with pytest.raises(ProviderError) as exc_info:
        _provider(session).list_files("o/r", "main")

    assert exc_info.value.kind is ProviderErrorKind.unexpected_response


def test_list_files_walk_reports_truncated_when_directory_hits_item_cap(
    monkeypatch,
) -> None:
    monkeypatch.setattr(client_module, "_CONTENTS_API_DIRECTORY_CAP", 2)
    session = _Session(
        [
            _Resp(200, json_data={"truncated": True, "tree": []}),
            _Resp(
                200,
                json_data=[
                    {"path": "p/a.rst", "type": "file"},
                    {"path": "p/b.rst", "type": "file"},
                ],
            ),
        ]
    )

    listing = _provider(session).list_files("o/r", "main")

    assert listing.paths == []
    assert listing.truncated is True
    assert "per-directory cap" in listing.truncated_reason
