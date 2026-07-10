import base64
import logging
import time

import requests

from tools.scanner.interfaces import DocProvider, FileListing
from tools.shared.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RepositoryError,
)

logger = logging.getLogger(__name__)

# HTTP request timeout (seconds) for every GitHub call.
_TIMEOUT = 30
# Max length of an error-response body we quote back in an exception message.
_ERROR_BODY_MAX = 200
# Seconds added past the rate-limit reset before retrying (clock-skew margin).
_RATE_LIMIT_BUFFER = 2
# Upper bound on a single rate-limit wait so a bogus reset can't hang the scan.
_MAX_RATE_LIMIT_WAIT = 3600


class GitHubDocProvider(DocProvider):
    def __init__(
        self, token: str, api_url: str, prefix: str, max_rate_limit_retries: int = 3
    ):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Accept"] = "application/vnd.github+json"
        self.api_url = api_url
        self.prefix = prefix
        # How many times to wait-out a rate limit before giving up on a call.
        self.max_rate_limit_retries = max_rate_limit_retries

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
        except NotFoundError:
            return False
        return True

    def list_files(self, repo: str, branch: str) -> FileListing:
        url = f"{self.api_url}/repos/{repo}/git/trees/{branch}"
        resp = self._get(
            url, repo=repo, resource=f"tree/{branch}", params={"recursive": "1"}
        )

        data = resp.json()
        truncated = bool(data.get("truncated"))
        if truncated:
            logger.warning(
                "Tree for %s@%s is truncated; some files may be missing",
                repo,
                branch,
            )
        paths = [
            item["path"]
            for item in data.get("tree", [])
            if item.get("type") == "blob"
            and item["path"].startswith(self.prefix)
            and item["path"].endswith(".rst")
        ]
        return FileListing(
            paths=paths,
            truncated=truncated,
            truncated_reason="GitHub git-tree response was truncated"
            if truncated
            else None,
        )

    def fetch_content(self, repo: str, path: str, branch: str) -> str:
        url = f"{self.api_url}/repos/{repo}/contents/{path}"
        resp = self._get(url, repo=repo, resource=path, params={"ref": branch})

        payload = resp.json()
        encoded = payload.get("content", "")
        return base64.b64decode(encoded).decode("utf-8")

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
        except NotFoundError:
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

        One place wraps the ``requests.RequestException`` → ``RepositoryError``
        translation and the status-code check. On a rate limit it waits out the
        reset and retries (up to ``max_rate_limit_retries``) so a scan runs to
        completion instead of aborting the moment the quota is hit.
        """
        attempts = 0
        while True:
            try:
                resp = self.session.get(url, timeout=_TIMEOUT, **kwargs)
            except requests.RequestException as e:
                raise RepositoryError(
                    f"GitHub request for {resource} in {repo} failed: {e}",
                    repo=repo,
                    cause=e,
                ) from e

            try:
                self._raise_for_status(resp, repo=repo, resource=resource)
            except RateLimitError as e:
                attempts += 1
                if attempts > self.max_rate_limit_retries:
                    raise
                wait = self._seconds_until_reset(e.reset_time)
                logger.warning(
                    "Rate limited on %s (%s); waiting %ds then retrying (%d/%d)",
                    resource,
                    repo,
                    wait,
                    attempts,
                    self.max_rate_limit_retries,
                )
                time.sleep(wait)
                continue

            return resp

    @staticmethod
    def _seconds_until_reset(reset_time: int | None) -> int:
        """Seconds to sleep until the rate-limit window resets (bounded)."""
        if not reset_time:
            return _RATE_LIMIT_BUFFER
        wait = reset_time - int(time.time()) + _RATE_LIMIT_BUFFER
        return max(0, min(wait, _MAX_RATE_LIMIT_WAIT))

    @staticmethod
    def _raise_for_status(resp: requests.Response, *, repo: str, resource: str) -> None:
        """Translate HTTP errors to typed domain exceptions."""
        if resp.status_code < 400:
            return
        if resp.status_code in (404, 409):
            raise NotFoundError(resource=resource, repo=repo)
        if resp.status_code == 401:
            raise AuthenticationError("Invalid or missing GitHub token", repo=repo)
        if resp.status_code == 403:
            # Distinguish rate-limit vs forbidden
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                raise RateLimitError(reset_time=reset)
            raise AuthenticationError(f"Forbidden when accessing {resource}", repo=repo)
        raise RepositoryError(
            f"Unexpected HTTP {resp.status_code} for {resource}: "
            f"{resp.text[:_ERROR_BODY_MAX]}",
            repo=repo,
        )
