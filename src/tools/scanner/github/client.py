import base64
import logging

import requests

from tools.domain.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RepositoryError,
)
from tools.domain.interfaces.doc_provider import DocProvider, FileListing

logger = logging.getLogger(__name__)

# HTTP request timeout (seconds) for every GitHub call.
_TIMEOUT = 30
# Max length of an error-response body we quote back in an exception message.
_ERROR_BODY_MAX = 200


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

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get(
        self, url: str, *, repo: str, resource: str, **kwargs
    ) -> requests.Response:
        """Issue a GET, mapping transport + HTTP errors to domain exceptions.

        One place wraps the ``requests.RequestException`` → ``RepositoryError``
        translation and the status-code check.
        """
        try:
            resp = self.session.get(url, timeout=_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            raise RepositoryError(
                f"GitHub request for {resource} in {repo} failed: {e}",
                repo=repo,
                cause=e,
            ) from e
        self._raise_for_status(resp, repo=repo, resource=resource)
        return resp

    @staticmethod
    def _raise_for_status(resp: requests.Response, *, repo: str, resource: str) -> None:
        """Translate HTTP errors to typed domain exceptions."""
        if resp.status_code < 400:
            return
        if resp.status_code == 404:
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
