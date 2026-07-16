"""Scanner-level tests using a fake DocProvider."""

from __future__ import annotations

from tools.domain.report.analytics import doc_overall_status
from tools.scanner.interfaces import FileListing
from tools.scanner.parsers import DocutilsParser, classify_doc_style
from tools.scanner.service import ScannerService
from tools.shared.exceptions import ProviderError, ProviderErrorKind
from tools.shared.ir import Endpoint, Service
from tools.shared.report import IssueCode
from tools.shared.repository import RepositoryInterruptionKind

from .conftest import load_fixture


class FakeDocProvider:
    """In-memory DocProvider for scanner tests."""

    def __init__(
        self,
        *,
        repos: dict[str, dict[str, str]],
        has_api_ref: set[str] | None = None,
        truncated: set[str] | None = None,
        commit_hash: str | None = "0" * 40,
        commit_error: str | None = None,
        path_error: str | None = None,
    ):
        # repos: {repo_name: {file_path: content}}
        self._repos = repos
        self._has_api_ref = (
            has_api_ref if has_api_ref is not None else set(repos.keys())
        )
        self._truncated = truncated or set()
        self._commit_hash = commit_hash
        self._commit_error = commit_error
        self._path_error = path_error
        self.calls: list[str] = []

    def list_repos(self, org: str) -> list[str]:
        self.calls.append(f"list_repos:{org}")
        return list(self._repos.keys())

    def path_exists(self, repo: str, branch: str, path: str) -> bool:
        self.calls.append(f"path_exists:{repo}@{branch}:{path}")
        if self._path_error:
            raise ProviderError(
                self._path_error,
                kind=ProviderErrorKind.unexpected_response,
                resource=repo,
            )
        return repo in self._has_api_ref

    def list_files(self, repo: str, branch: str) -> FileListing:
        self.calls.append(f"list_files:{repo}@{branch}")
        return FileListing(
            paths=list(self._repos.get(repo, {}).keys()),
            truncated=repo in self._truncated,
            truncated_reason="mocked truncation" if repo in self._truncated else None,
        )

    def fetch_content(self, repo: str, path: str, branch: str) -> str:
        self.calls.append(f"fetch_content:{repo}@{branch}:{path}")
        return self._repos[repo][path]

    def get_commit_hash(self, repo: str, branch: str) -> str | None:
        self.calls.append(f"get_commit_hash:{repo}@{branch}")
        if self._commit_error:
            raise ProviderError(
                self._commit_error,
                kind=ProviderErrorKind.unexpected_response,
                resource=repo,
            )
        return self._commit_hash


def make_scanner(fake: FakeDocProvider, **kwargs) -> ScannerService:
    """Construct a ScannerService with the real classifier + test defaults."""
    kwargs.setdefault("parser", DocutilsParser())
    kwargs.setdefault("style_classifier", classify_doc_style)
    kwargs.setdefault("max_workers", 4)
    kwargs.setdefault("api_ref_path", "api-ref/source")
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
    result = scanner.scan_organization(org="o")
    assert result.skipped_repos == ["o/svc-b"]
    assert {r.repository.repo for r in result.repos} == {"o/svc-a"}
    assert [call for call in fake.calls if call.startswith("path_exists:")] == [
        "path_exists:o/svc-a@" + "0" * 40 + ":api-ref/source",
        "path_exists:o/svc-b@" + "0" * 40 + ":api-ref/source",
    ]
    assert fake.calls.index("get_commit_hash:o/svc-a@main") < fake.calls.index(
        "path_exists:o/svc-a@" + "0" * 40 + ":api-ref/source"
    )


def test_eligible_count_excludes_skipped() -> None:
    fake = FakeDocProvider(
        repos={"o/a": {}, "o/b": {}, "o/c": {}},
        has_api_ref={"o/a", "o/c"},
    )
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o")
    assert result.total_repos == 3
    assert result.eligible_repos == 2


# --------------------------------------------------------------------------- #
# commit_hash (S2)
# --------------------------------------------------------------------------- #
def test_commit_hash_emitted() -> None:
    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}},
        commit_hash="a" * 40,
    )
    result = make_scanner(fake).scan_organization(org="o")
    repo = result.repos[0]
    assert repo.commit_hash == "a" * 40
    # Present in the serialized report, not just the model.
    assert result.model_dump(mode="json")["repos"][0]["commit_hash"] == "a" * 40


def test_commit_hash_error_stops_before_eligibility_and_scan() -> None:
    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}},
        commit_error="commit lookup failed",
    )
    result = make_scanner(fake).scan_organization(org="o")
    repo = result.repos[0]
    assert repo.commit_hash is None
    assert not isinstance(repo.repository, Service)
    assert repo.error == "Could not resolve commit for o/cce@main: commit lookup failed"
    assert repo.document_results == []
    assert fake.calls == ["list_repos:o", "get_commit_hash:o/cce@main"]


def _refs_used_by_scan(commit_hash: str | None) -> list[str]:
    """Run a scan and return every ref the provider was asked to read at."""
    seen: list[str] = []

    class _Recording(FakeDocProvider):
        def list_files(self, repo: str, branch: str) -> FileListing:
            seen.append(branch)
            return super().list_files(repo, branch)

        def fetch_content(self, repo: str, path: str, branch: str) -> str:
            seen.append(branch)
            return super().fetch_content(repo, path, branch)

    provider = _Recording(
        repos={"o/cce": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}},
        commit_hash=commit_hash,
    )
    make_scanner(provider).scan_organization(org="o")
    return seen


def test_scan_reads_tree_and_files_at_resolved_commit() -> None:
    # Every content read is pinned to the resolved SHA, not the branch name, so
    # a push mid-scan can't diverge the content from the recorded commit_hash.
    refs = _refs_used_by_scan("a" * 40)
    assert refs and all(ref == "a" * 40 for ref in refs)


def test_scan_falls_back_to_branch_when_commit_hash_unknown() -> None:
    refs = _refs_used_by_scan(None)
    assert refs and all(ref == "main" for ref in refs)


# --------------------------------------------------------------------------- #
# Single-repository scan (S1)
# --------------------------------------------------------------------------- #
def test_scan_repository_checks_eligibility_at_resolved_commit() -> None:
    sha = "a" * 40
    path = "api-ref/source/x.rst"
    fake = FakeDocProvider(
        repos={"o/cce": {path: load_fixture("style_a_cce_grid.rst")}},
        commit_hash=sha,
    )

    result = make_scanner(fake).scan_repository("o/cce", branch="main")

    assert isinstance(result.repository, Service)
    assert result.commit_hash == sha
    assert result.document_results
    assert fake.calls == [
        "get_commit_hash:o/cce@main",
        f"path_exists:o/cce@{sha}:api-ref/source",
        f"list_files:o/cce@{sha}",
        f"fetch_content:o/cce@{sha}:{path}",
    ]


def test_scan_repository_returns_ineligible_without_scanning() -> None:
    sha = "a" * 40
    fake = FakeDocProvider(
        repos={"o/empty": {"api-ref/source/x.rst": "unused"}},
        has_api_ref=set(),
        commit_hash=sha,
    )

    result = make_scanner(fake).scan_repository("o/empty")

    assert not isinstance(result.repository, Service)
    assert result.error is None
    assert result.document_results == []
    assert result.documents_by_version == {}
    assert result.non_endpoint_documents == []
    assert result.excluded_documents == []
    assert fake.calls == [
        "get_commit_hash:o/empty@main",
        f"path_exists:o/empty@{sha}:api-ref/source",
    ]


def test_unresolved_commit_and_missing_path_is_not_normal_ineligible() -> None:
    fake = FakeDocProvider(
        repos={"o/missing": {}},
        has_api_ref=set(),
        commit_hash=None,
    )

    result = make_scanner(fake).scan_repository("o/missing", branch="bad-ref")

    assert not isinstance(result.repository, Service)
    assert result.commit_hash is None
    assert result.error == (
        "Cannot confirm o/missing@bad-ref: commit could not be resolved and "
        "api-ref/source was not found"
    )
    assert fake.calls == [
        "get_commit_hash:o/missing@bad-ref",
        "path_exists:o/missing@bad-ref:api-ref/source",
    ]


def test_unresolved_commit_with_existing_path_scans_original_ref() -> None:
    path = "api-ref/source/x.rst"
    fake = FakeDocProvider(
        repos={"o/cce": {path: load_fixture("style_a_cce_grid.rst")}},
        commit_hash=None,
    )

    result = make_scanner(fake).scan_repository("o/cce", branch="develop")

    assert isinstance(result.repository, Service)
    assert result.commit_hash is None
    assert result.document_results
    assert fake.calls == [
        "get_commit_hash:o/cce@develop",
        "path_exists:o/cce@develop:api-ref/source",
        "list_files:o/cce@develop",
        f"fetch_content:o/cce@develop:{path}",
    ]


def test_eligibility_error_stops_before_file_listing() -> None:
    sha = "a" * 40
    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": "unused"}},
        commit_hash=sha,
        path_error="eligibility lookup failed",
    )

    result = make_scanner(fake).scan_repository("o/cce")

    assert not isinstance(result.repository, Service)
    assert result.error == (
        f"Could not check eligibility for o/cce@{sha}: eligibility lookup failed"
    )
    assert result.interruption is not None
    assert result.interruption.kind is RepositoryInterruptionKind.repository_failure
    assert result.interruption.repository == "o/cce"
    assert result.model_dump(mode="json")["interruption"] == {
        "kind": "repository_failure",
        "repository": "o/cce",
        "message": "eligibility lookup failed",
        "reset_time": None,
    }
    assert fake.calls == [
        "get_commit_hash:o/cce@main",
        f"path_exists:o/cce@{sha}:api-ref/source",
    ]


def test_scan_repository_repeated_call_preserves_result_contract() -> None:
    fake = FakeDocProvider(repos={"o/empty": {}}, has_api_ref=set())
    scanner = make_scanner(fake)

    first = scanner.scan_repository("o/empty").model_dump(mode="json")
    second = scanner.scan_repository("o/empty").model_dump(mode="json")

    assert second == first


def test_scan_repository_matches_repos_element_shape() -> None:
    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}}
    )
    scanner = make_scanner(fake)

    repo_result = scanner.scan_repository(repo="o/cce", branch="main")
    org = scanner.scan_organization(org="o")

    # Same type and same serialised shape as an element of the org report's
    # repos[], so F2 ingest accepts it unchanged.
    assert type(repo_result) is type(org.repos[0])
    assert repo_result.model_dump(mode="json").keys() == (
        org.repos[0].model_dump(mode="json").keys()
    )
    assert repo_result.repository.repo == "o/cce"
    assert isinstance(repo_result.repository, Service)
    assert len(repo_result.document_results) == 1


def test_scan_repository_captures_error_without_raising() -> None:
    class ListFailProvider(FakeDocProvider):
        def list_files(self, repo: str, branch: str) -> FileListing:
            raise ProviderError(
                "tree fetch failed",
                kind=ProviderErrorKind.unexpected_response,
                resource=repo,
            )

    scanner = make_scanner(ListFailProvider(repos={"o/x": {}}))
    repo_result = scanner.scan_repository(repo="o/x", branch="main")
    assert repo_result.error == "tree fetch failed"
    assert repo_result.document_results == []


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
    result = scanner.scan_organization(org="o")
    repo = result.repos[0]
    docs = repo.document_results
    assert len(docs) == 1
    doc = docs[0]
    assert doc.failure_reason is None
    # CCE's `metadata` object resolves to its struct table, so the doc is fully
    # extracted now (no deferred-nesting partial) and emits no nested_objects.
    assert doc_overall_status(doc, repo.section_results) == "ok"
    assert isinstance(doc.document, Endpoint)
    assert repo.repository.documents == [doc.document]
    sections = {section.name: section for section in doc.document.sections}
    assert "path_params" in sections
    assert "body" in sections
    assert "nested_objects" not in sections
    metadata = sections["body"].parameters[0]
    assert metadata.name == "metadata"
    assert [c.name for c in metadata.children] == ["name"]
    assert doc.document.api_version == "v3"


def test_obs_marked_unsupported() -> None:
    fake = FakeDocProvider(
        repos={"o/obs": {"api-ref/source/x.rst": load_fixture("style_b_obs.rst")}}
    )
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o")
    repo = result.repos[0]
    doc = repo.document_results[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.UNSUPPORTED_DOC_STYLE
    assert doc_overall_status(doc, repo.section_results) == "unsupported"
    assert not isinstance(doc.document, Endpoint)


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
    result = scanner.scan_organization(org="o")
    repo = result.repos[0]
    assert repo.non_endpoint_documents == ["api-ref/source/intro.rst"]
    assert len(repo.document_results) == 1
    assert repo.document_results[0].document.path == "api-ref/source/real.rst"


def test_fetch_failure_is_gating() -> None:
    class FailingProvider(FakeDocProvider):
        def fetch_content(self, repo: str, path: str, branch: str) -> str:
            raise RuntimeError("network down")

    fake = FailingProvider(
        repos={"o/svc": {"api-ref/source/x.rst": ""}},
    )
    scanner = make_scanner(fake)
    result = scanner.scan_organization(org="o")
    repo = result.repos[0]
    doc = repo.document_results[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.FETCH_FAILED
    assert doc_overall_status(doc, repo.section_results) == "failed"


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
    result = scanner.scan_organization(org="o")
    repo = result.repos[0]
    doc = repo.document_results[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.PARSER_ERROR
    assert doc_overall_status(doc, repo.section_results) == "failed"


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
    result = scanner.scan_organization(org="o")
    repo = result.repos[0]
    assert repo.non_endpoint_documents == []
    doc = repo.document_results[0]
    assert doc.failure_reason is not None
    assert doc.failure_reason.code is IssueCode.NO_URI_MATCH
    assert doc_overall_status(doc, repo.section_results) == "failed"


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
    result = scanner.scan_organization(org="o")
    repo = result.repos[0]
    # Excluded file is not parsed, not counted as a non_endpoint doc...
    assert all(
        "out-of-date_apis" not in result.document.path
        for result in repo.document_results
    )
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
    result = scanner.scan_organization(org="o")
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
    result = scanner.scan_organization(org="o")
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
    result = scanner.scan_organization(org="o")
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
    result = scanner.scan_organization(org="o")
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
    result = scanner.scan_organization(org="o")

    assert result.report_schema_version == REPORT_SCHEMA_VERSION >= 3
    assert result.scanner_version == __version__
    assert result.repos[0].scanner_version == __version__
    # Present in the serialized JSON, not just the model.
    dumped = result.model_dump(mode="json")
    assert dumped["scanner_version"] == __version__
    assert dumped["repos"][0]["scanner_version"] == __version__
