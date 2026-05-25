from typing import Protocol


class DocProvider(Protocol):
    def list_repos(self, org: str) -> list[str]:
        """Return list of repositories (full_name) belonging to an organization."""
        ...

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        """Return True if the given path exists in the repo at the given branch."""
        ...

    def list_files(self, repo: str, branch: str) -> list[str]:
        """Return paths to RST files in the repo (filtered by configured prefix)."""
        ...

    def fetch_content(self, repo: str, path: str, branch: str) -> str:
        """Return the textual content of a file in the repo at the given branch."""
        ...
