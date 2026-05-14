import base64
import logging

import requests

from tools.domain.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RepositoryError,
)
from tools.domain.interfaces.doc_provider import DocProvider

logger = logging.getLogger(__name__)


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
            url = f"{self.api_url}/orgs/{org}/repos"
            params = {"per_page": 100, "page": page, "type": "public"}
            try:
                resp = self.session.get(url, params=params, timeout=30)
                self._raise_for_status(resp, repo=org, resource=f"orgs/{org}/repos")
            except requests.RequestException as e:
                raise RepositoryError(
                    f"Failed to list repos for org {org}: {e}",
                    repo=org,
                    cause=e,
                ) from e

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
            resp = self.session.get(url, params={"ref": branch}, timeout=30)
        except requests.RequestException as e:
            raise RepositoryError(
                f"Failed to check path '{path}' in {repo}: {e}",
                repo=repo,
                cause=e,
            ) from e

        if resp.status_code == 404:
            return False
        # Surface auth/rate-limit errors clearly rather than treating them as "missing"
        self._raise_for_status(resp, repo=repo, resource=path)
        return True

    def list_files(self, repo: str, branch: str) -> list[str]:
        url = f"{self.api_url}/repos/{repo}/git/trees/{branch}"
        try:
            resp = self.session.get(url, params={"recursive": "1"}, timeout=30)
            self._raise_for_status(resp, repo=repo, resource=f"tree/{branch}")
        except requests.RequestException as e:
            raise RepositoryError(
                f"Failed to list files in {repo}@{branch}: {e}",
                repo=repo,
                cause=e,
            ) from e

        data = resp.json()
        if data.get("truncated"):
            logger.warning(
                "Tree for %s@%s is truncated; some files may be missing",
                repo,
                branch,
            )
        return [
            item["path"]
            for item in data.get("tree", [])
            if item.get("type") == "blob"
            and item["path"].startswith(self.prefix)
            and item["path"].endswith(".rst")
        ]

    def fetch_content(self, repo: str, path: str) -> str:
        url = f"{self.api_url}/repos/{repo}/contents/{path}"
        try:
            resp = self.session.get(url, timeout=30)
            self._raise_for_status(resp, repo=repo, resource=path)
        except requests.RequestException as e:
            raise RepositoryError(
                f"Failed to fetch {path} from {repo}: {e}",
                repo=repo,
                cause=e,
            ) from e

        payload = resp.json()
        encoded = payload.get("content", "")
        return base64.b64decode(encoded).decode("utf-8")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
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
            f"Unexpected HTTP {resp.status_code} for {resource}: {resp.text[:200]}",
            repo=repo,
        )
