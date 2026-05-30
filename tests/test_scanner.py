"""Scanner-level tests using a fake DocProvider."""

from __future__ import annotations

from tools.domain.report import IssueCode
from tools.domain.services.scanner import ScannerService
from tools.infrastructure.parsers.doc_parser import DocutilsParser

from .conftest import load_fixture


class FakeDocProvider:
    """In-memory DocProvider for scanner tests."""

    def __init__(
        self,
        *,
        repos: dict[str, dict[str, str]],
        has_api_ref: set[str] | None = None,
    ):
        # repos: {repo_name: {file_path: content}}
        self._repos = repos
        self._has_api_ref = (
            has_api_ref if has_api_ref is not None else set(repos.keys())
        )

    def list_repos(self, org: str) -> list[str]:
        return list(self._repos.keys())

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        return repo in self._has_api_ref

    def list_files(self, repo: str, branch: str) -> list[str]:
        return list(self._repos.get(repo, {}).keys())

    def fetch_content(self, repo: str, path: str, branch: str) -> str:
        return self._repos[repo][path]


# --------------------------------------------------------------------------- #
# Org-level filtering
# --------------------------------------------------------------------------- #
def test_skips_repo_without_api_ref() -> None:
    fake = FakeDocProvider(
        repos={"o/svc-a": {}, "o/svc-b": {}},
        has_api_ref={"o/svc-a"},  # only svc-a has api-ref
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    assert result.skipped_repos == ["o/svc-b"]
    assert {r.repo for r in result.repos} == {"o/svc-a"}


def test_eligible_count_excludes_skipped() -> None:
    fake = FakeDocProvider(
        repos={"o/a": {}, "o/b": {}, "o/c": {}},
        has_api_ref={"o/a", "o/c"},
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    assert result.total_repos == 3
    assert result.eligible_repos == 2


# --------------------------------------------------------------------------- #
# Per-document outcomes
# --------------------------------------------------------------------------- #
def test_style_a_populates_sections() -> None:
    fake = FakeDocProvider(
        repos={
            "o/cce": {
                "api-ref/source/foo.rst": load_fixture("style_a_cce_grid.rst"),
            }
        }
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    docs = result.repos[0].documents
    assert len(docs) == 1
    doc = docs[0]
    assert doc.failure_reason is None
    assert doc.overall_status == "ok"
    assert "path_params" in doc.sections
    assert "body" in doc.sections
    assert doc.api_version == "v3"


def test_obs_marked_unsupported() -> None:
    fake = FakeDocProvider(
        repos={"o/obs": {"api-ref/source/x.rst": load_fixture("style_b_obs.rst")}}
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    doc = result.repos[0].documents[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.UNSUPPORTED_DOC_STYLE
    assert doc.overall_status == "unsupported"
    assert doc.sections == {}


def test_non_endpoint_recorded() -> None:
    fake = FakeDocProvider(
        repos={
            "o/svc": {
                "api-ref/source/intro.rst": "Intro\n=====\n\nNothing endpoint-y.\n",
                "api-ref/source/real.rst": load_fixture("style_a_cce_grid.rst"),
            }
        }
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    repo = result.repos[0]
    assert repo.non_endpoint_documents == ["api-ref/source/intro.rst"]
    assert len(repo.documents) == 1
    assert repo.documents[0].document == "api-ref/source/real.rst"


def test_fetch_failure_is_gating() -> None:
    class FailingProvider(FakeDocProvider):
        def fetch_content(self, repo: str, path: str, branch: str) -> str:
            raise RuntimeError("network down")

    fake = FailingProvider(
        repos={"o/svc": {"api-ref/source/x.rst": ""}},
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    doc = result.repos[0].documents[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.FETCH_FAILED
    assert doc.overall_status == "failed"


# --------------------------------------------------------------------------- #
# Excluded segments
# --------------------------------------------------------------------------- #
def test_excluded_segments_drop_paths() -> None:
    fake = FakeDocProvider(
        repos={
            "o/svc": {
                "api-ref/source/out-of-date_apis/old.rst": "old",
                "api-ref/source/real.rst": load_fixture("style_a_cce_grid.rst"),
            }
        }
    )
    scanner = ScannerService(
        doc_provider=fake,
        parser=DocutilsParser(),
        excluded_segments=["out-of-date_apis"],
    )
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    repo = result.repos[0]
    # out-of-date file is dropped silently, not even recorded as non_endpoint
    assert all("out-of-date_apis" not in d.document for d in repo.documents)
    assert "out-of-date_apis" not in str(repo.non_endpoint_documents)


def test_excluded_default_empty() -> None:
    """A scanner constructed with no excluded_segments scans everything."""
    scanner = ScannerService(
        doc_provider=FakeDocProvider(repos={}),
        parser=DocutilsParser(),
    )
    assert scanner.excluded_segments == frozenset()


def test_excluded_segments_not_shared() -> None:
    """Two instances built with the same default get distinct frozensets."""
    a = ScannerService(
        doc_provider=FakeDocProvider(repos={}),
        parser=DocutilsParser(),
        excluded_segments=["x"],
    )
    b = ScannerService(
        doc_provider=FakeDocProvider(repos={}),
        parser=DocutilsParser(),
        excluded_segments=["x"],
    )
    assert a.excluded_segments == b.excluded_segments
    assert a.excluded_segments is not b.excluded_segments


# --------------------------------------------------------------------------- #
# documents_by_version
# --------------------------------------------------------------------------- #
def test_by_version_groups_parsed() -> None:
    fake = FakeDocProvider(
        repos={
            "o/cce": {
                "api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst"),
            },
        }
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    repo = result.repos[0]
    assert "v3" in repo.documents_by_version
    assert len(repo.documents_by_version["v3"]) == 1


def test_by_version_excludes_failed() -> None:
    """Failed/unsupported docs do not appear in documents_by_version."""
    fake = FakeDocProvider(
        repos={
            "o/svc": {
                "api-ref/source/obs.rst": load_fixture("style_b_obs.rst"),
            }
        }
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    assert result.repos[0].documents_by_version == {}


# --------------------------------------------------------------------------- #
# Org-level quality summary
# --------------------------------------------------------------------------- #
def test_quality_summary_counts() -> None:
    fake = FakeDocProvider(
        repos={
            "o/cce": {
                "api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst"),
            },
            "o/obs": {
                "api-ref/source/y.rst": load_fixture("style_b_obs.rst"),
            },
        }
    )
    scanner = ScannerService(doc_provider=fake, parser=DocutilsParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    qs = result.quality_summary
    assert qs.by_overall_status.get("ok", 0) >= 1
    assert qs.by_overall_status.get("unsupported", 0) == 1
