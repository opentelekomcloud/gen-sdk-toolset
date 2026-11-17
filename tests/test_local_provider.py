"""Reading a documentation repository from a local git working copy."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.scanner.local import LocalDocProvider, LocalSourceError
from tools.shared.exceptions import ProviderError, ProviderErrorKind

PREFIX = "api-ref/source/"


def _provider(root: Path) -> LocalDocProvider:
    return LocalDocProvider(root, prefix=PREFIX)


def test_lists_only_rst_files_under_the_prefix(make_git_repo) -> None:
    root = make_git_repo(
        {
            "api-ref/source/b.rst": "b",
            "api-ref/source/sub/a.rst": "a",
            "api-ref/source/notes.txt": "not rst",
            "umn/source/other.rst": "outside the prefix",
        }
    )

    listing = _provider(root).list_files("ignored", "ignored")

    assert listing.paths == ["api-ref/source/b.rst", "api-ref/source/sub/a.rst"]
    assert listing.truncated is False


def test_missing_prefix_lists_nothing(make_git_repo) -> None:
    root = make_git_repo({"README.md": "no api-ref"})

    assert _provider(root).list_files("r", "b").paths == []
    assert _provider(root).path_exists("r", "b", "api-ref/source") is False


def test_reads_the_working_tree_not_the_commit(make_git_repo) -> None:
    """The local scan checks edits before they are committed."""
    root = make_git_repo({"api-ref/source/a.rst": "committed"})
    (root / "api-ref/source/a.rst").write_text("edited", encoding="utf-8")

    provider = _provider(root)

    assert provider.fetch_content("r", "api-ref/source/a.rst", "sha") == "edited"
    assert provider.path_exists("r", "sha", "api-ref/source/") is True


def test_commit_and_branch_come_from_head(make_git_repo) -> None:
    root = make_git_repo({"api-ref/source/a.rst": "a"})
    provider = _provider(root)

    commit = provider.get_commit_hash("r", "ignored")

    assert commit is not None and len(commit) == 40
    assert provider.current_branch() == "main"


def test_uncommitted_changes_are_detected_under_the_path_only(make_git_repo) -> None:
    root = make_git_repo({"api-ref/source/a.rst": "a", "README.md": "r"})
    provider = _provider(root)
    assert provider.has_uncommitted_changes("api-ref/source") is False

    (root / "README.md").write_text("changed outside", encoding="utf-8")
    assert provider.has_uncommitted_changes("api-ref/source") is False

    (root / "api-ref/source/new.rst").write_text("untracked", encoding="utf-8")
    assert provider.has_uncommitted_changes("api-ref/source") is True


def test_folder_outside_git_is_rejected(tmp_path: Path) -> None:
    provider = _provider(tmp_path)

    with pytest.raises(LocalSourceError, match="git working copy"):
        provider.get_commit_hash("r", "b")


def test_missing_folder_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(LocalSourceError, match="not a directory"):
        _provider(tmp_path / "absent")


def test_undecodable_file_is_left_to_the_per_document_fallback(make_git_repo) -> None:
    root = make_git_repo({"api-ref/source/a.rst": "a"})
    (root / "api-ref/source/a.rst").write_bytes(b"\xff\xfe broken")

    with pytest.raises(UnicodeDecodeError):
        _provider(root).fetch_content("r", "api-ref/source/a.rst", "sha")


def test_file_gone_after_listing_fails_the_read(make_git_repo) -> None:
    root = make_git_repo({"api-ref/source/a.rst": "a"})
    provider = _provider(root)

    with pytest.raises(ProviderError) as exc_info:
        provider.fetch_content("r", "api-ref/source/gone.rst", "sha")

    assert exc_info.value.kind is ProviderErrorKind.not_found
    assert exc_info.value.resource == "api-ref/source/gone.rst"


def test_unreadable_file_fails_the_read(make_git_repo, monkeypatch) -> None:
    root = make_git_repo({"api-ref/source/a.rst": "a"})

    def _denied(self):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "read_bytes", _denied)

    with pytest.raises(ProviderError) as exc_info:
        _provider(root).fetch_content("r", "api-ref/source/a.rst", "sha")

    assert exc_info.value.kind is ProviderErrorKind.permission_denied
