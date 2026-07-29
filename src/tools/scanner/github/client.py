from __future__ import annotations

import base64
import logging

import requests

from tools.scanner.interfaces import DocProvider, FileListing
from tools.shared.exceptions import ProviderError, ProviderErrorKind

logger = logging.getLogger(__name__)

# HTTP request timeout (seconds) for every GitHub call.
_TIMEOUT = 30
# Max length of an error-response body we quote back in an exception message.
_ERROR_BODY_MAX = 200
# Cap on directory-listing calls the truncated-tree fallback walk (see
# list_files) will make before giving up rather than risk exhausting the
# rate-limit budget for the rest of an org-wide scan on one pathological repo.
_MAX_WALK_REQUESTS = 300
# The Contents API's own undocumented per-directory item cap. Unlike the
# git-trees endpoint, a directory listing at or above this size carries no
# explicit truncation signal - a directory this large is treated as itself
# incomplete rather than trusted as the full listing.
_CONTENTS_API_DIRECTORY_CAP = 1000


class _IncompleteWalk(Exception):
    """Internal signal: the directory-walk fallback could not guarantee a
    complete listing (request budget exhausted, or a directory hit the
    Contents API's own undocumented per-directory item cap).

    Not a ProviderError - this is the walk's own bookkeeping, not an upstream
    failure, so it must not be caught by callers that only expect ProviderError.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class GitHubDocProvider(DocProvider):
    def __init__(self, token: str, api_url: str, prefix: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Accept"] = "application/vnd.github+json"
        self.api_url = api_url
        self.prefix = prefix

    # ------------------------------------------------------------------ #
    # Public DocProvider methods
    # ------------------------------------------------------------------ #
    def list_repos(self, org: str) -> list[str]:
        """List all non-archived repositories for an organization (paginated)."""
        repos: list[str] = []
        page = 1
        while True:
            resp = self._get(
                f"{self.api_url}/orgs/{org}/repos",
                repo=org,
                resource=f"orgs/{org}/repos",
                params={"per_page": 100, "page": page, "type": "public"},
            )
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break

            repos.extend(
                item["full_name"] for item in batch if not item.get("archived")
            )

            if len(batch) < 100:
                break
            page += 1

        logger.info("Discovered %d repos in org %s", len(repos), org)
        return repos

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        """Check whether `path` exists in `repo` at `branch`."""
        url = f"{self.api_url}/repos/{repo}/contents/{path.rstrip('/')}"
        try:
            self._get(url, repo=repo, resource=path, params={"ref": branch})
        except ProviderError as error:
            if error.kind is not ProviderErrorKind.not_found:
                raise
            return False
        return True

    def list_files(self, repo: str, branch: str) -> FileListing:
        """Return the RST file paths under `self.prefix` in `repo` at `branch`.

        GitHub's recursive tree endpoint caps huge trees and reports
        ``truncated: true`` instead of erroring. When that happens, this
        falls back to walking `self.prefix` directory-by-directory via the
        Contents API - scoped to that prefix rather than the whole repo,
        since that is the only subtree the scanner cares about, and bounded
        by `_MAX_WALK_REQUESTS` so one huge repo cannot exhaust the org
        scan's rate-limit budget, and guards against the Contents API's own
        undocumented per-directory item cap (`_CONTENTS_API_DIRECTORY_CAP`).
        If the walk cannot finish within budget, or a directory is at or
        above that cap, this reports `truncated=True` rather than a partial
        listing - a listing that gave up partway is not a complete one
        either.
        """
        url = f"{self.api_url}/repos/{repo}/git/trees/{branch}"
        resp = self._get(
            url, repo=repo, resource=f"tree/{branch}", params={"recursive": "1"}
        )

        data = resp.json()
        if not bool(data.get("truncated")):
            paths = [
                item["path"]
                for item in data.get("tree", [])
                if item.get("type") == "blob"
                and item["path"].startswith(self.prefix)
                and item["path"].endswith(".rst")
            ]
            return FileListing(paths=paths)

        logger.warning(
            "Tree for %s@%s is truncated; falling back to a directory walk of %r",
            repo,
            branch,
            self.prefix,
        )
        try:
            paths = self._walk_prefix(repo, branch)
        except _IncompleteWalk as e:
            logger.error("File listing for %s is still incomplete: %s", repo, e.reason)
            return FileListing(truncated=True, truncated_reason=e.reason)
        return FileListing(paths=paths)

    def _walk_prefix(self, repo: str, branch: str) -> list[str]:
        """Reconstruct the RST paths under `self.prefix` directory-by-directory.

        Iterative rather than recursive, so an unusually deep doc tree can
        never risk Python's recursion limit. Raises `_IncompleteWalk` if
        `_MAX_WALK_REQUESTS` is exhausted, or a directory is at or above
        `_CONTENTS_API_DIRECTORY_CAP`, before the walk completes. A genuine
        `ProviderError` from any directory listing propagates uncaught,
        exactly like the top-level tree call above.
        """
        paths: list[str] = []
        stack = [self.prefix.rstrip("/")]
        requests_made = 0
        while stack:
            directory = stack.pop()
            if requests_made >= _MAX_WALK_REQUESTS:
                raise _IncompleteWalk(
                    f"directory walk of {self.prefix!r} exceeded "
                    f"{_MAX_WALK_REQUESTS} requests without completing"
                )
            requests_made += 1
            entries = self._list_directory(repo, branch, directory)
            if len(entries) >= _CONTENTS_API_DIRECTORY_CAP:
                raise _IncompleteWalk(
                    f"directory {directory!r} returned {len(entries)} entries, "
                    f"at or above the Contents API's own undocumented "
                    f"per-directory cap (~{_CONTENTS_API_DIRECTORY_CAP}); "
                    "the listing may be incomplete"
                )
            for entry in entries:
                self._collect_entry(entry, repo=repo, paths=paths, stack=stack)
        return paths

    @staticmethod
    def _collect_entry(
        entry: dict, *, repo: str, paths: list[str], stack: list[str]
    ) -> None:
        """Route one Contents API entry into the walk's paths or its stack.

        The four documented types are handled explicitly. A submodule's content
        lives in another repository, so it is not part of this snapshot and is
        skipped rather than read. An `.rst` path of any other type means the
        API returned something this walk does not understand - that fails the
        scan rather than being guessed at, since a listing we cannot classify
        is not one we can call complete.
        """
        entry_type = entry.get("type")
        path = entry["path"]

        if entry_type == "dir":
            stack.append(path)
            return
        if entry_type == "submodule":
            logger.debug("Skipping submodule %s in %s", path, repo)
            return
        if not path.endswith(".rst"):
            return
        if entry_type not in ("file", "symlink"):
            raise ProviderError(
                f"Unexpected Contents API type {entry_type!r} for {path} in {repo}",
                kind=ProviderErrorKind.unexpected_response,
                resource=path,
            )
        paths.append(path)

    def _list_directory(self, repo: str, branch: str, path: str) -> list[dict]:
        """Return the immediate child entries of one directory."""
        url = f"{self.api_url}/repos/{repo}/contents/{path}"
        resp = self._get(url, repo=repo, resource=path, params={"ref": branch})
        data = resp.json()
        if not isinstance(data, list):
            raise ProviderError(
                f"Expected a directory listing at {path} in {repo}, "
                f"got {type(data).__name__}",
                kind=ProviderErrorKind.unexpected_response,
                resource=path,
            )
        return data

    def fetch_content(self, repo: str, path: str, branch: str) -> str:
        """Return the text content of `path`.

        Only a regular file is readable here. Up to 1 MB the Contents API
        inlines it as base64; above that (to the API's 100 MB ceiling) it
        reports ``encoding: "none"`` and omits the content, and this retries
        the same request with the raw media type to get the bytes directly.
        Any other type or encoding is something this client cannot read, and
        raises rather than being guessed at.
        """
        url = f"{self.api_url}/repos/{repo}/contents/{path}"
        resp = self._get(url, repo=repo, resource=path, params={"ref": branch})

        payload = resp.json()
        entry_type = payload.get("type")
        encoding = payload.get("encoding")
        if entry_type != "file":
            raise ProviderError(
                f"Expected a file at {path} in {repo}, got type {entry_type!r}",
                kind=ProviderErrorKind.unexpected_response,
                resource=path,
            )
        if encoding == "base64":
            return base64.b64decode(payload.get("content", "")).decode("utf-8")
        if encoding != "none":
            raise ProviderError(
                f"Unexpected content encoding {encoding!r} for {path} in {repo}",
                kind=ProviderErrorKind.unexpected_response,
                resource=path,
            )

        logger.info(
            "Contents API omitted inline data for %s in %s (over the 1 MB"
            " inline limit); retrying with the raw media type",
            path,
            repo,
        )
        raw_resp = self._get(
            url,
            repo=repo,
            resource=path,
            params={"ref": branch},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        # A decode failure here is a bad document, not a transport failure -
        # let it propagate bare, exactly like the base64 branch above, so
        # ScannerService gates only this one document instead of failing
        # the whole repository scan (see _fetch_document's except clauses).
        return raw_resp.content.decode("utf-8")

    def get_commit_hash(self, repo: str, branch: str) -> str | None:
        """Head commit SHA of `branch`, or None if the ref can't be resolved.

        Uses the commits listing capped at one entry so the response stays
        small (the single-commit endpoint would carry the full diff).
        """
        url = f"{self.api_url}/repos/{repo}/commits"
        try:
            resp = self._get(
                url,
                repo=repo,
                resource=f"commits@{branch}",
                params={"sha": branch, "per_page": 1},
            )
        except ProviderError as error:
            if error.kind is not ProviderErrorKind.not_found:
                raise
            return None
        commits = resp.json()
        if isinstance(commits, list) and commits:
            return commits[0].get("sha")
        return None

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get(
        self, url: str, *, repo: str, resource: str, **kwargs
    ) -> requests.Response:
        """Issue a GET, mapping transport + HTTP errors to domain exceptions.

        One place wraps the ``requests.RequestException`` → ``ProviderError``
        translation and the status-code check. Rate-limit responses are exposed
        immediately so the caller can own any retry policy.
        """
        try:
            resp = self.session.get(url, timeout=_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            raise ProviderError(
                f"GitHub request for {resource} in {repo} failed: {e}",
                kind=ProviderErrorKind.connection_error,
                resource=resource,
                cause=e,
            ) from e

        self._raise_for_status(resp, repo=repo, resource=resource)
        return resp

    @staticmethod
    def _raise_for_status(resp: requests.Response, *, repo: str, resource: str) -> None:
        """Translate HTTP errors to typed domain exceptions."""
        if resp.status_code < 400:
            return
        if resp.status_code in (404, 409):
            raise ProviderError(
                f"Not found: {resource}",
                kind=ProviderErrorKind.not_found,
                status_code=resp.status_code,
                resource=resource,
            )
        if resp.status_code == 401:
            raise ProviderError(
                "Invalid or missing GitHub token",
                kind=ProviderErrorKind.authentication,
                status_code=resp.status_code,
                resource=resource,
            )
        if resp.status_code in (403, 429):
            remaining = resp.headers.get("X-RateLimit-Remaining")
            rate_limited = (
                resp.status_code == 429
                or remaining == "0"
                or "Retry-After" in resp.headers
                or "rate limit" in resp.text.lower()
            )
            if rate_limited:
                reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                raise ProviderError(
                    "GitHub API rate limit exceeded",
                    kind=ProviderErrorKind.rate_limit,
                    status_code=resp.status_code,
                    resource=resource,
                    reset_time=reset or None,
                )
            raise ProviderError(
                f"Forbidden when accessing {resource}",
                kind=ProviderErrorKind.permission_denied,
                status_code=resp.status_code,
                resource=resource,
            )
        raise ProviderError(
            f"Unexpected HTTP {resp.status_code} for {resource}: "
            f"{resp.text[:_ERROR_BODY_MAX]}",
            kind=ProviderErrorKind.unexpected_response,
            status_code=resp.status_code,
            resource=resource,
        )
