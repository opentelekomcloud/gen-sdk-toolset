from typing import Protocol

class DocProvider(Protocol):
    def list_files(self, repo: str, branch: str) -> list[str]:
        """Получить список путей к RST файлам."""
        ...

    def fetch_content(self, repo: str, path: str) -> str:
        """Получить содержимое конкретного файла."""
        ...
