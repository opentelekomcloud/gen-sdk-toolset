"""Read a documentation repository from a folder on disk.

The result is labelled with ``HEAD``, but files are read from the working tree,
uncommitted edits included: the local scan exists to check edits before they
are merged.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools.scanner.interfaces import DocProvider, FileListing
from tools.shared.exceptions import GenSdkError, ProviderError, ProviderErrorKind


class LocalSourceError(GenSdkError):
    """The folder cannot be scanned: missing, not a git working copy, or git failed."""


class LocalDocProvider(DocProvider):
    """:class:`DocProvider` over one local git working copy.

    The ``repo`` and ``branch`` arguments of the protocol methods are accepted
    for compatibility and ignored: there is exactly one repository, and its
    contents are always the working tree.
    """

    def __init__(self, root: Path, prefix: str):
        root = Path(root)
        if not root.is_dir():
            raise LocalSourceError(f"{root} is not a directory")
        self.root = root.resolve()
        self.prefix = prefix

    def list_repos(self, org: str) -> list[str]:
        raise NotImplementedError("a local folder holds exactly one repository")

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        return (self.root / path.rstrip("/")).exists()

    def list_files(self, repo: str, branch: str) -> FileListing:
        base = self.root / self.prefix
        if not base.is_dir():
            return FileListing()
        paths = sorted(
            file.relative_to(self.root).as_posix()
            for file in base.rglob("*.rst")
            if file.is_file()
        )
        return FileListing(paths=paths)

    def fetch_content(self, repo: str, path: str, branch: str) -> str:
        try:
            content = (self.root / path).read_bytes()
        except OSError as e:
            # A file that cannot be read means the scan did not see the whole
            # copy: fail the scan instead of reporting a partial result.
            raise ProviderError(
                f"Cannot read {path}: {e}",
                kind=_io_error_kind(e),
                resource=path,
                cause=e,
            ) from e
        # A decode failure is a bad document, not a failed snapshot: let it
        # reach the scanner's per-document fallback, as the GitHub provider does.
        return content.decode("utf-8")

    def get_commit_hash(self, repo: str, branch: str) -> str | None:
        return self._git("rev-parse", "HEAD")

    def current_branch(self) -> str:
        """Name of the checked-out branch, or ``HEAD`` when detached."""
        return self._git("rev-parse", "--abbrev-ref", "HEAD")

    def has_uncommitted_changes(self, path: str) -> bool:
        """True when files under ``path`` differ from ``HEAD`` (untracked included)."""
        return bool(self._git("status", "--porcelain", "--", path.rstrip("/")))

    def _git(self, *args: str) -> str:
        try:
            completed = subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise LocalSourceError("git is not installed") from e
        if completed.returncode != 0:
            message = completed.stderr.strip() or f"git {' '.join(args)} failed"
            raise LocalSourceError(
                f"{self.root} is not a usable git working copy: {message}"
            )
        return completed.stdout.strip()


def _io_error_kind(error: OSError) -> ProviderErrorKind:
    if isinstance(error, FileNotFoundError):
        return ProviderErrorKind.not_found
    if isinstance(error, PermissionError):
        return ProviderErrorKind.permission_denied
    return ProviderErrorKind.unexpected_response
