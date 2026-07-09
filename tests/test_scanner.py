"""Scanner-level tests using a fake DocProvider."""

from __future__ import annotations

from tools.scanner.interfaces import FileListing
from tools.domain.report import IssueCode
from tools.scanner.parsers import DocutilsParser, classify_doc_style
from tools.scanner.service import ScannerService

from .conftest import load_fixture


class FakeDocProvider:
    """In-memory DocProvider for scanner tests."""

    def __init__(
        self,
        *,
        repos: dict[str, dict[str, str]],
        has_api_ref: set[str] | None = None,
        truncated: set[str] | None = None,
    ):
        # repos: {repo_name: {file_path: content}}
        self._repos = repos
        self._has_api_ref = (
            has_api_ref if has_api_ref is not None else set(repos.keys())
        )
        self._truncated = truncated or set()

    def list_repos(self, org: str) -> list[str]:
        return list(self._repos.keys())

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        return repo in self._has_api_ref

    def list_files(self, repo: str, branch: str) -> FileListing:
        return FileListing(
            paths=list(self._repos.get(repo, {}).keys()),
            truncated=repo in self._truncated,
            truncated_reason="mocked truncation" if repo in self._truncated else None,
        )

    def fetch_content(self, repo: str, path: str, branch: str) -> str:
        return self._repos[repo][path]


def make_scanner(fake: FakeDocProvider, **kwargs) -> ScannerService:
    """Construct a ScannerService with the real classifier + test defaults."""
    kwargs.setdefault("parser", DocutilsParser())
    kwargs.setdefault("style_classifier", classify_doc_style)
    kwargs.setdefault("max_workers", 4)
    return ScannerService(doc_provider=fake, **kwargs)


# --------------------------------------------------------------------------- #
# Org-level filtering
# --------------------------------------------------------------------------- #
def test_skips_repo_without_api_ref() -> None:
    fake = FakeDocProvider(
        repos={"o/svc-a": {}, "o/svc-b": {}},
        has_api_ref={"o/svc-a"},  # only svc-a has api-ref
    )
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    assert result.skipped_repos == ["o/svc-b"]
    assert {r.repo for r in result.repos} == {"o/svc-a"}


def test_eligible_count_excludes_skipped() -> None:
    fake = FakeDocProvider(
        repos={"o/a": {}, "o/b": {}, "o/c": {}},
        has_api_ref={"o/a", "o/c"},
    )
    scanner = make_scanner(fake)
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
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    docs = result.repos[0].documents
    assert len(docs) == 1
    doc = docs[0]
    assert doc.failure_reason is None
    # CCE's `metadata` object resolves to its struct table, so the doc is fully
    # extracted now (no deferred-nesting partial) and emits no nested_objects.
    assert doc.overall_status == "ok"
    assert "path_params" in doc.sections
    assert "body" in doc.sections
    assert "nested_objects" not in doc.sections
    metadata = doc.sections["body"].parameters[0]
    assert metadata.name == "metadata"
    assert [c.name for c in metadata.children] == ["name"]
    assert doc.api_version == "v3"


def test_obs_marked_unsupported() -> None:
    fake = FakeDocProvider(
        repos={"o/obs": {"api-ref/source/x.rst": load_fixture("style_b_obs.rst")}}
    )
    scanner = make_scanner(fake)
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
    scanner = make_scanner(fake)
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
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    doc = result.repos[0].documents[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.FETCH_FAILED
    assert doc.overall_status == "failed"


def test_parser_crash_is_parser_error() -> None:
    """An unexpected parser exception is reported as parser_error, never as
    no_uri_match."""

    class CrashingParser(DocutilsParser):
        def parse(self, content: str, path: str):
            raise RuntimeError("boom")

    fake = FakeDocProvider(
        repos={"o/svc": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}}
    )
    scanner = make_scanner(fake, parser=CrashingParser())
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    doc = result.repos[0].documents[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.PARSER_ERROR
    assert doc.overall_status == "failed"


def test_endpoint_doc_without_uri_is_failed() -> None:
    """A doc with a URI section heading but no extractable method+path must
    surface as failed/no_uri_match, not silently drop into non_endpoint."""
    content = (
        "Some Endpoint\n=============\n\n"
        "URI\n---\n\n"
        "The endpoint is described in prose, with no METHOD path line.\n"
    )
    fake = FakeDocProvider(repos={"o/svc": {"api-ref/source/x.rst": content}})
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    repo = result.repos[0]
    assert repo.non_endpoint_documents == []
    doc = repo.documents[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.NO_URI_MATCH
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
    scanner = make_scanner(fake, excluded_segments=["out-of-date_apis"])
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    repo = result.repos[0]
    # Excluded file is not parsed, not counted as a non_endpoint doc...
    assert all("out-of-date_apis" not in d.document for d in repo.documents)
    assert "out-of-date_apis" not in str(repo.non_endpoint_documents)
    assert repo.excluded_documents == ["api-ref/source/out-of-date_apis/old.rst"]


def test_excluded_default_empty() -> None:
    """A scanner constructed with no excluded_segments scans everything."""
    scanner = make_scanner(FakeDocProvider(repos={}))
    assert scanner.excluded_segments == frozenset()


def test_excluded_segments_not_shared() -> None:
    """Two instances built with the same default get distinct frozensets."""
    a = make_scanner(FakeDocProvider(repos={}), excluded_segments=["x"])
    b = make_scanner(FakeDocProvider(repos={}), excluded_segments=["x"])
    assert a.excluded_segments == b.excluded_segments
    assert a.excluded_segments is not b.excluded_segments


# --------------------------------------------------------------------------- #
# Truncated tree → incomplete repo
# --------------------------------------------------------------------------- #
def test_truncated_tree_marks_repo_incomplete() -> None:
    fake = FakeDocProvider(
        repos={"o/svc": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}},
        truncated={"o/svc"},
    )
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    repo = result.repos[0]
    assert repo.incomplete is True
    assert repo.incomplete_reason


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
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    repo = result.repos[0]
    assert "v3" in repo.documents_by_version
    assert len(repo.documents_by_version["v3"]) == 1
    # Org-level computed aggregation mirrors the per-repo grouping (item 12).
    assert result.by_version == {"v3": 1}


def test_by_version_excludes_failed() -> None:
    """Failed/unsupported docs do not appear in documents_by_version."""
    fake = FakeDocProvider(
        repos={
            "o/svc": {
                "api-ref/source/obs.rst": load_fixture("style_b_obs.rst"),
            }
        }
    )
    scanner = make_scanner(fake)
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
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")
    qs = result.quality_summary
    # CCE is ok (nested struct resolved), OBS is unsupported.
    assert qs.by_overall_status.get("ok", 0) >= 1
    assert qs.by_overall_status.get("unsupported", 0) == 1


# --------------------------------------------------------------------------- #
# Scanner version stamped on the report (review addition A)
# --------------------------------------------------------------------------- #
def test_report_stamps_scanner_version() -> None:
    """Every report carries the scanner version + bumped schema version, so
    report diffing can tell 'docs changed' from 'parser improved'."""
    from tools import __version__
    from tools.domain.report import REPORT_SCHEMA_VERSION

    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}}
    )
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o", api_ref_path="api-ref/source")

    assert result.report_schema_version == REPORT_SCHEMA_VERSION >= 3
    assert result.scanner_version == __version__
    assert result.repos[0].scanner_version == __version__
    # Present in the serialized JSON, not just the model.
    dumped = result.model_dump(mode="json")
    assert dumped["scanner_version"] == __version__
    assert dumped["repos"][0]["scanner_version"] == __version__
