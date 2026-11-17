"""Public CLI behavior for a single-repository scan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.config import Settings
from tools.scanner import main as scanner_main
from tools.shared.ir import Repository, Service
from tools.shared.scan import (
    RepositoryInterruption,
    RepositoryInterruptionKind,
    RepositoryScanResult,
)

from .conftest import load_fixture


class FakeScanner:
    def __init__(self, *, repo_result: RepositoryScanResult):
        self.repo_result = repo_result
        self.calls: list[tuple[str, str, str]] = []

    def scan_repository(self, repo: str, branch: str = "main") -> RepositoryScanResult:
        self.calls.append(("repo", repo, branch))
        return self.repo_result


def _settings() -> Settings:
    return Settings(
        github_token="test-token",
        github={"org": "default-org", "branch": "main"},
        output={"path": "default-output.json", "indent": 2},
    )


def _install_fakes(monkeypatch, scanner: FakeScanner) -> None:
    settings = _settings()
    monkeypatch.setattr(scanner_main, "_load_settings_or_exit", lambda _path: settings)
    monkeypatch.setattr(scanner_main, "build_scanner", lambda _settings: scanner)


def _fail_before_scanner(*_args, **_kwargs):
    pytest.fail("settings or scanner creation must not run for invalid arguments")


def test_missing_repo_is_a_usage_error_before_scanner_creation(monkeypatch) -> None:
    """--repo is the only scan target, so omitting it must fail on argument
    parsing rather than after loading settings or reaching for a token."""
    monkeypatch.setattr(scanner_main, "_load_settings_or_exit", _fail_before_scanner)
    monkeypatch.setattr(scanner_main, "build_scanner", _fail_before_scanner)

    with pytest.raises(SystemExit) as exc_info:
        scanner_main.main(["--output", "-"])

    assert exc_info.value.code == scanner_main.EXIT_USAGE_ERROR


def test_repo_stdout_is_one_raw_repo_result(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    result = RepositoryScanResult(
        repository=Service(repo="o/name"),
        branch="main",
        commit_hash="a" * 40,
    )
    scanner = FakeScanner(repo_result=result)
    _install_fakes(monkeypatch, scanner)

    exit_code = scanner_main.main(["--repo", "o/name", "--output", "-"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == scanner_main.EXIT_OK
    assert RepositoryScanResult.model_validate(payload) == result
    assert scanner.calls == [("repo", "o/name", "main")]
    assert list(tmp_path.iterdir()) == []
    # Derived, org-level views belong to the panel: the scanner emits data only.
    assert {
        "org",
        "total_repos",
        "eligible_repos",
        "skipped_repos",
        "repos",
        "report_schema_version",
        "total_documents",
        "quality_summary",
    }.isdisjoint(payload)


def test_repo_file_contains_same_json_as_stdout(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    result = RepositoryScanResult(
        repository=Service(repo="o/name"),
        branch="feature",
    )
    scanner = FakeScanner(repo_result=result)
    _install_fakes(monkeypatch, scanner)

    assert (
        scanner_main.main(["--repo", "o/name", "--branch", "feature", "--output", "-"])
        == scanner_main.EXIT_OK
    )
    stdout_payload = json.loads(capsys.readouterr().out)

    output_path = tmp_path / "repo.json"
    assert (
        scanner_main.main(
            [
                "--repo",
                "o/name",
                "--branch",
                "feature",
                "--output",
                str(output_path),
            ]
        )
        == scanner_main.EXIT_OK
    )

    assert capsys.readouterr().out == ""
    assert json.loads(output_path.read_text(encoding="utf-8")) == stdout_payload


def test_ineligible_repo_is_a_successful_empty_result(monkeypatch, capsys) -> None:
    result = RepositoryScanResult(
        repository=Repository(repo="o/name"),
        branch="main",
    )
    scanner = FakeScanner(repo_result=result)
    _install_fakes(monkeypatch, scanner)

    exit_code = scanner_main.main(["--repo", "o/name", "--output", "-"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == scanner_main.EXIT_OK
    assert "documents" not in payload["repository"]
    assert payload["error"] is None
    assert "document_results" not in payload
    assert "section_results" not in payload


@pytest.mark.parametrize(
    "error",
    [
        "Cannot confirm o/name@bad-ref: repository or ref is unresolved",
        "tree fetch failed",
    ],
)
def test_repo_diagnostic_error_is_serialized_and_returns_runtime_error(
    error: str, monkeypatch, capsys
) -> None:
    result = RepositoryScanResult(
        repository=Repository(repo="o/name"),
        branch="bad-ref",
        error=error,
    )
    scanner = FakeScanner(repo_result=result)
    _install_fakes(monkeypatch, scanner)

    exit_code = scanner_main.main(
        ["--repo", "o/name", "--branch", "bad-ref", "--output", "-"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == scanner_main.EXIT_RUNTIME_ERROR
    assert payload["error"] == error


def test_repo_interruption_returns_runtime_error(monkeypatch, capsys) -> None:
    result = RepositoryScanResult(
        repository=Repository(repo="o/name"),
        branch="main",
        interruption=RepositoryInterruption(
            kind=RepositoryInterruptionKind.rate_limit,
            repository="o/name",
            message="rate limited",
        ),
    )
    scanner = FakeScanner(repo_result=result)
    _install_fakes(monkeypatch, scanner)

    exit_code = scanner_main.main(["--repo", "o/name", "--output", "-"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == scanner_main.EXIT_RUNTIME_ERROR
    assert payload["error"] is None
    assert payload["interruption"]["message"] == "rate limited"


def test_org_flag_is_rejected(monkeypatch) -> None:
    """Organization scanning moved to the panel; the flag must fail loudly
    rather than being silently accepted and ignored."""
    monkeypatch.setattr(scanner_main, "_load_settings_or_exit", _fail_before_scanner)
    monkeypatch.setattr(scanner_main, "build_scanner", _fail_before_scanner)

    with pytest.raises(SystemExit) as exc_info:
        scanner_main.main(["--org", "o", "--output", "-"])

    assert exc_info.value.code == scanner_main.EXIT_USAGE_ERROR


# --- --path: scan a local working copy ---------------------------------------


def _local_settings() -> Settings:
    return Settings(github_token=None, output={"path": "scan.json", "indent": 2})


def test_path_scans_without_a_token_and_prints_the_report(
    monkeypatch, tmp_path: Path, capsys, make_git_repo
) -> None:
    root = make_git_repo(
        {"api-ref/source/doc_errors.rst": load_fixture("doc_checks/doc_errors.rst")}
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    monkeypatch.chdir(out_dir)
    monkeypatch.setattr(
        scanner_main, "_load_settings_or_exit", lambda _path: _local_settings()
    )

    exit_code = scanner_main.main(["--path", str(root)])
    report = capsys.readouterr().out

    assert exit_code == scanner_main.EXIT_OK
    assert report.startswith(f"# API reference scan: {root.name}\n")
    assert "## api-ref/source/doc_errors.rst" in report
    assert "`flavors_id`" in report
    assert "changes after this commit" not in report
    saved = RepositoryScanResult.model_validate_json(
        (out_dir / "scan.json").read_text(encoding="utf-8")
    )
    assert saved.branch == "main"
    assert saved.commit_hash is not None


def test_path_report_mentions_uncommitted_changes(
    monkeypatch, tmp_path: Path, capsys, make_git_repo
) -> None:
    root = make_git_repo({"api-ref/source/a.rst": "Title\n=====\n"})
    (root / "api-ref/source/a.rst").write_text("Edited\n======\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        scanner_main, "_load_settings_or_exit", lambda _path: _local_settings()
    )

    assert scanner_main.main(["--path", str(root)]) == scanner_main.EXIT_OK
    assert "changes after this commit" in capsys.readouterr().out


def test_path_without_api_reference_says_so(
    monkeypatch, tmp_path: Path, capsys, make_git_repo
) -> None:
    root = make_git_repo({"README.md": "no docs"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        scanner_main, "_load_settings_or_exit", lambda _path: _local_settings()
    )

    assert scanner_main.main(["--path", str(root)]) == scanner_main.EXIT_OK
    assert "No API reference found under `api-ref/source`" in capsys.readouterr().out


def test_path_outside_git_is_a_usage_error(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        scanner_main, "_load_settings_or_exit", lambda _path: _local_settings()
    )

    exit_code = scanner_main.main(["--path", str(tmp_path)])

    assert exit_code == scanner_main.EXIT_USAGE_ERROR
    assert "git working copy" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    [
        ["--repo", "o/name"],
        ["--branch", "dev"],
        ["--stdout"],
        ["--output", "-"],
    ],
)
def test_path_conflicting_flags_fail_before_settings(monkeypatch, extra) -> None:
    monkeypatch.setattr(scanner_main, "_load_settings_or_exit", _fail_before_scanner)

    with pytest.raises(SystemExit) as exc_info:
        scanner_main.main(["--path", ".", *extra])

    assert exc_info.value.code == scanner_main.EXIT_USAGE_ERROR


def test_path_unreadable_file_fails_the_scan_instead_of_a_clean_report(
    monkeypatch, tmp_path: Path, capsys, make_git_repo
) -> None:
    """A file the scan could not read must not end as "no errors found"."""
    root = make_git_repo(
        {"api-ref/source/doc_errors.rst": load_fixture("doc_checks/doc_errors.rst")}
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        scanner_main, "_load_settings_or_exit", lambda _path: _local_settings()
    )
    original = Path.read_bytes

    def _deny_rst(self):
        if self.suffix == ".rst":
            raise PermissionError(13, "Permission denied", str(self))
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", _deny_rst)

    exit_code = scanner_main.main(["--path", str(root)])

    assert exit_code == scanner_main.EXIT_RUNTIME_ERROR
    assert "No documentation errors found." not in capsys.readouterr().out
    saved = RepositoryScanResult.model_validate_json(
        (tmp_path / "scan.json").read_text(encoding="utf-8")
    )
    assert "Cannot read api-ref/source/doc_errors.rst" in saved.failure_message
