from typing import Protocol


class DocProvider(Protocol):
    def list_files(self, repo: str, branch: str) -> list[str]:
        """Receive paths to RST files"""
        ...

    def fetch_content(self, repo: str, path: str) -> str:
        """Get content for specific file."""
        ...
