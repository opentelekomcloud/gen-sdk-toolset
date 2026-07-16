"""Public CLI behavior for repository and legacy organization scans."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.config import Settings
from tools.domain.report import OrgScanResult
from tools.scanner import main as scanner_main
from tools.shared.ir import Repository, Service
from tools.shared.scan import RepositoryScanResult


class FakeScanner:
    def __init__(
        self,
        *,
        repo_result: RepositoryScanResult | None = None,
        org_result: OrgScanResult | None = None,
    ):
        self.repo_result = repo_result
        self.org_result = org_result
        self.calls: list[tuple[str, str, str]] = []

    def scan_repository(self, repo: str, branch: str = "main") -> RepositoryScanResult:
        self.calls.append(("repo", repo, branch))
        assert self.repo_result is not None
        return self.repo_result

    def scan_organization(self, org: str, branch: str = "main") -> OrgScanResult:
        self.calls.append(("org", org, branch))
        assert self.org_result is not None
        return self.org_result


def _settings() -> Settings:
    return Settings(
        github_token="test-token",
        github={"org": "default-org", "branch": "main"},
        output={"path": "default-output.json", "indent": 2},
    )


def _install_fakes(monkeypatch, scanner: FakeScanner) -> None:
    settings = _settings()
    monkeypatch.setattr(scanner_main, "_load_settings_or_exit", lambda _path: settings)
    monkeypatch.setattr(scanner_main, "_build_scanner", lambda _settings: scanner)


def _fail_before_scanner(*_args, **_kwargs):
    pytest.fail("settings or scanner creation must not run for invalid arguments")


def test_repo_and_org_are_mutually_exclusive_before_scanner_creation(
    monkeypatch,
) -> None:
    monkeypatch.setattr(scanner_main, "_load_settings_or_exit", _fail_before_scanner)
    monkeypatch.setattr(scanner_main, "_build_scanner", _fail_before_scanner)

    with pytest.raises(SystemExit) as exc_info:
        scanner_main.main(["--repo", "o/name", "--org", "o"])

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


def test_legacy_org_mode_still_emits_org_result(monkeypatch, capsys) -> None:
    result = OrgScanResult(org="o", branch="develop", total_repos=0)
    scanner = FakeScanner(org_result=result)
    _install_fakes(monkeypatch, scanner)

    exit_code = scanner_main.main(
        ["--org", "o", "--branch", "develop", "--output", "-"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == scanner_main.EXIT_OK
    assert OrgScanResult.model_validate(payload).org == "o"
    assert scanner.calls == [("org", "o", "develop")]
