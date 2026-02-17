import base64

import requests
from gen_sdk_tooling.domain.interfaces.doc_provider import DocProvider
from gen_sdk_tooling.domain.exceptions import NotFoundError, RateLimitError, RepositoryError  #


class GitHubDocProvider(DocProvider):
    def __init__(self, token: str, api_url: str, prefix: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.api_url = api_url
        self.prefix = prefix

    def list_files(self, repo: str, branch: str) -> list[str]:
        try:
            url = f"{self.api_url}/repos/{repo}/git/trees/{branch}?recursive=1"
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return [
                item["path"] for item in resp.json().get("tree", [])
                if item["path"].startswith(self.prefix) and item["path"].endswith(".rst")
            ]
        except Exception as e:
            raise RepositoryError(f"Failed to list files: {e}", repo=repo)

    def fetch_content(self, repo: str, path: str) -> str:
        try:
            resp = self.session.get(
                f"{self.api_url}/repos/{repo}/contents/{path}",
                timeout=30)
            resp.raise_for_status()
            return base64.b64decode(resp.json()["content"]).decode("utf-8")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise NotFoundError(resource=path, repo=repo) from e  #
            if e.response.status_code == 403:
                # Читаем заголовки GitHub для reset_time
                reset = int(e.response.headers.get("X-RateLimit-Reset", 0))
                raise RateLimitError(reset_time=reset) from e  #
            raise RepositoryError(f"Unexpected error: {e}", repo=repo)  #
