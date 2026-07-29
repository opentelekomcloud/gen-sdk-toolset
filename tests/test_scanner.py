"""Scanner-level tests using a fake DocProvider."""

from __future__ import annotations

from tools.panel.core.analytics.generation import document_status
from tools.scanner.interfaces import FileListing
from tools.scanner.parsers import DocutilsParser, classify_doc_style
from tools.scanner.service import ScannerService
from tools.shared.exceptions import ProviderError, ProviderErrorKind
from tools.shared.ir import Endpoint, SectionName, Service
from tools.shared.scan import (
    IssueCode,
    RepositoryInterruptionKind,
    RepositoryScanResult,
    SectionStatus,
)

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
# commit_hash (S2)
# --------------------------------------------------------------------------- #
def test_commit_hash_emitted() -> None:
    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}},
        commit_hash="a" * 40,
    )
    result = make_scanner(fake).scan_repository("o/cce")
    assert result.commit_hash == "a" * 40
    # Present in the serialized result, not just the model.
    assert result.model_dump(mode="json")["commit_hash"] == "a" * 40


def test_commit_hash_error_stops_before_eligibility_and_scan() -> None:
    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}},
        commit_error="commit lookup failed",
    )
    result = make_scanner(fake).scan_repository("o/cce")
    assert result.commit_hash is None
    assert not isinstance(result.repository, Service)
    assert (
        result.error == "Could not resolve commit for o/cce@main: commit lookup failed"
    )
    assert fake.calls == ["get_commit_hash:o/cce@main"]


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
    make_scanner(provider).scan_repository("o/cce")
    return seen


def test_scan_reads_tree_and_files_at_resolved_commit() -> None:
    # Every content read is pinned to the resolved SHA, not the branch name, so
    # a push mid-scan can't diverge the content from the recorded commit_hash.
    refs = _refs_used_by_scan("a" * 40)
    assert refs and all(ref == "a" * 40 for ref in refs)


def test_no_content_is_read_when_commit_hash_unresolved() -> None:
    # An unresolvable commit stops the scan before any file listing or
    # content fetch — there is no safe branch-name fallback to read at.
    assert _refs_used_by_scan(None) == []


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
    assert result.repository.documents
    assert fake.calls == [
        "get_commit_hash:o/cce@main",
        f"path_exists:o/cce@{sha}:api-ref/source",
        f"list_files:o/cce@{sha}",
        f"fetch_content:o/cce@{sha}:{path}",
    ]


def test_scan_repository_ignores_duplicate_provider_paths() -> None:
    class DuplicatePathProvider(FakeDocProvider):
        def list_files(self, repo: str, branch: str) -> FileListing:
            listing = super().list_files(repo, branch)
            return FileListing(paths=listing.paths * 2)

    path = "api-ref/source/x.rst"
    fake = DuplicatePathProvider(
        repos={"o/cce": {path: load_fixture("style_a_cce_grid.rst")}}
    )

    result = make_scanner(fake).scan_repository("o/cce")

    assert isinstance(result.repository, Service)
    assert len(result.repository.documents) == 1
    assert fake.calls.count(f"fetch_content:o/cce@{'0' * 40}:{path}") == 1


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
    assert result.excluded_documents == []
    assert fake.calls == [
        "get_commit_hash:o/empty@main",
        f"path_exists:o/empty@{sha}:api-ref/source",
    ]


def test_unresolved_commit_stops_before_eligibility_regardless_of_path() -> None:
    """An unresolved commit is gating on its own: the scan must not fall back
    to checking (or scanning) the plain branch name, even when the api-ref
    path would in fact exist there."""
    path = "api-ref/source/x.rst"
    fake = FakeDocProvider(
        repos={"o/cce": {path: load_fixture("style_a_cce_grid.rst")}},
        commit_hash=None,
    )

    result = make_scanner(fake).scan_repository("o/cce", branch="develop")

    assert not isinstance(result.repository, Service)
    assert result.commit_hash is None
    assert result.error == (
        "Could not resolve commit for o/cce@develop: commit SHA could not be resolved"
    )
    assert fake.calls == ["get_commit_hash:o/cce@develop"]


def test_eligibility_error_stops_before_file_listing() -> None:
    sha = "a" * 40
    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": "unused"}},
        commit_hash=sha,
        path_error="eligibility lookup failed",
    )

    result = make_scanner(fake).scan_repository("o/cce")

    assert not isinstance(result.repository, Service)
    assert result.error is None
    assert result.failure_message == "eligibility lookup failed"
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
    assert isinstance(repo_result.repository, Service)
    assert repo_result.repository.documents == []


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
    result = scanner.scan_repository("o/cce")
    assert isinstance(result.repository, Service)
    docs = result.repository.documents
    assert len(docs) == 1
    doc = docs[0]
    assert doc.scan_result.failure_reason is None
    assert isinstance(doc, Endpoint)
    sections = {section.name: section for section in doc.sections}
    # This fixture writes its example request and response as bold run-ins,
    # which the parser drops. `document_status` judges a document on its
    # parameter tables only, so that loss does not degrade the status - but it
    # must still be recorded on the example sections rather than vanish.
    assert document_status(doc) == "ok"
    assert any(
        sections[name].scan_result.status is not SectionStatus.OK
        for name in (SectionName.EXAMPLE_REQUEST, SectionName.EXAMPLE_RESPONSE)
    )
    assert len(sections) == 7
    assert "path_params" in sections
    assert "body" in sections
    assert "nested_objects" not in sections
    metadata = sections["body"].parameters[0]
    assert metadata.name == "metadata"
    assert [c.name for c in metadata.children] == ["name"]
    assert doc.api_version == "v3"


def test_obs_marked_unsupported() -> None:
    fake = FakeDocProvider(
        repos={"o/obs": {"api-ref/source/x.rst": load_fixture("style_b_obs.rst")}}
    )
    scanner = make_scanner(fake)
    result = scanner.scan_repository("o/obs")
    assert isinstance(result.repository, Service)
    doc = result.repository.documents[0]
    assert doc.scan_result.failure_reason is not None
    assert doc.scan_result.failure_reason.code is IssueCode.UNSUPPORTED_DOC_STYLE
    assert document_status(doc) == "unsupported"
    assert not isinstance(doc, Endpoint)


def test_non_endpoint_materialized_as_document() -> None:
    fake = FakeDocProvider(
        repos={
            "o/svc": {
                "api-ref/source/intro.rst": "Intro\n=====\n\nNothing endpoint-y.\n",
                "api-ref/source/real.rst": load_fixture("style_a_cce_grid.rst"),
            }
        }
    )
    scanner = make_scanner(fake)
    result = scanner.scan_repository("o/svc")
    assert "non_endpoint_documents" not in RepositoryScanResult.model_fields
    assert isinstance(result.repository, Service)
    assert len(result.repository.documents) == 2
    documents = {document.path: document for document in result.repository.documents}
    intro = documents["api-ref/source/intro.rst"]
    assert not isinstance(intro, Endpoint)
    assert intro.title == "Intro"
    assert intro.scan_result.failure_reason is None
    assert isinstance(documents["api-ref/source/real.rst"], Endpoint)


def test_successful_endpoint_title_is_extracted_only_by_parser(monkeypatch) -> None:
    def fail_if_called(content: str) -> str | None:
        raise AssertionError("scanner must not extract title for a parsed endpoint")

    monkeypatch.setattr(
        "tools.scanner.service.extract_document_title",
        fail_if_called,
    )
    fake = FakeDocProvider(
        repos={
            "o/svc": {
                "api-ref/source/endpoint.rst": load_fixture("style_a_cce_grid.rst")
            }
        }
    )

    result = make_scanner(fake).scan_repository("o/svc")

    assert isinstance(result.repository, Service)
    endpoint = result.repository.documents[0]
    assert isinstance(endpoint, Endpoint)
    assert endpoint.title is not None


def test_repository_context_resolves_table_from_non_endpoint_document() -> None:
    overview = """Overview
========

.. _shared_fields:

.. table:: Shared fields

   =========  ======  ===========
   Parameter  Type    Description
   =========  ======  ===========
   id         String  object ID
   name       String  object name
   =========  ======  ===========
"""
    endpoint = """Query object
============

URI
---

GET /v1/objects/{id}

Response
--------

.. table:: Response parameters

   =========  ======  ===========
   Parameter  Type    Description
   =========  ======  ===========
   object     Object  result
   =========  ======  ===========

For details about the **object** field, see :ref:`Shared <shared_fields>`.
"""
    fake = FakeDocProvider(
        repos={
            "o/svc": {
                "api-ref/source/overview.rst": overview,
                "api-ref/source/query.rst": endpoint,
            }
        }
    )

    result = make_scanner(fake).scan_repository("o/svc")

    assert isinstance(result.repository, Service)
    parsed = next(
        document
        for document in result.repository.documents
        if document.path.endswith("query.rst")
    )
    assert isinstance(parsed, Endpoint)
    response = next(
        section for section in parsed.sections if section.name == "response"
    )
    assert [child.name for child in response.parameters[0].children] == ["id", "name"]


def test_fetch_failure_is_gating() -> None:
    """A non-ProviderError fetch failure gates only this document.

    ProviderError is different - see
    test_scan_repository_fails_when_fetch_raises_provider_error - because it
    means the transport itself is unreliable, not that this one document is
    bad.
    """

    class FailingProvider(FakeDocProvider):
        def fetch_content(self, repo: str, path: str, branch: str) -> str:
            raise RuntimeError("network down")

    fake = FailingProvider(
        repos={"o/svc": {"api-ref/source/x.rst": ""}},
    )
    scanner = make_scanner(fake)
    result = scanner.scan_repository("o/svc")
    assert isinstance(result.repository, Service)
    doc = result.repository.documents[0]
    assert doc.scan_result.failure_reason is not None
    assert doc.scan_result.failure_reason.code is IssueCode.FETCH_FAILED
    assert document_status(doc) == "failed"


def test_scan_repository_fails_when_fetch_raises_provider_error() -> None:
    """A transport failure while fetching content must fail the whole
    repository scan rather than being reported as a per-document parse
    problem: the pinned snapshot could not be read in full."""

    class TransportFailingProvider(FakeDocProvider):
        def fetch_content(self, repo: str, path: str, branch: str) -> str:
            raise ProviderError(
                "connection reset",
                kind=ProviderErrorKind.connection_error,
                resource=path,
            )

    fake = TransportFailingProvider(
        repos={"o/svc": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}}
    )

    result = make_scanner(fake).scan_repository("o/svc")

    assert isinstance(result.repository, Service)
    assert result.repository.documents == []
    assert (
        result.error == "Failed to fetch document content for o/svc: connection reset"
    )


def test_fetch_provider_error_voids_the_whole_scan() -> None:
    """One transport failure must void the whole snapshot, even when another
    document in the same repository fetched cleanly - a partially-fetched
    repo is not a documentation-quality result."""

    class FlakyProvider(FakeDocProvider):
        def fetch_content(self, repo: str, path: str, branch: str) -> str:
            if path.endswith("bad.rst"):
                raise ProviderError(
                    "connection reset",
                    kind=ProviderErrorKind.connection_error,
                    resource=path,
                )
            return super().fetch_content(repo, path, branch)

    fake = FlakyProvider(
        repos={
            "o/svc": {
                "api-ref/source/good.rst": load_fixture("style_a_cce_grid.rst"),
                "api-ref/source/bad.rst": "unused",
            }
        }
    )

    result = make_scanner(fake).scan_repository("o/svc")

    assert isinstance(result.repository, Service)
    assert result.repository.documents == []
    assert result.error is not None


def test_non_utf8_content_gates_only_that_document() -> None:
    """A document whose raw bytes aren't valid UTF-8 (e.g. a large file read
    via the raw-media-type fallback) gates only itself: the client raises a
    plain UnicodeDecodeError, not a ProviderError, so this is a document
    problem - not a transport one - exactly like test_fetch_failure_is_gating's
    generic case, not test_fetch_provider_error_voids_the_whole_scan's."""

    class BadEncodingProvider(FakeDocProvider):
        def fetch_content(self, repo: str, path: str, branch: str) -> str:
            if path.endswith("bad.rst"):
                raise UnicodeDecodeError(
                    "utf-8", b"\xff\xfe", 0, 1, "invalid start byte"
                )
            return super().fetch_content(repo, path, branch)

    fake = BadEncodingProvider(
        repos={
            "o/svc": {
                "api-ref/source/good.rst": load_fixture("style_a_cce_grid.rst"),
                "api-ref/source/bad.rst": "unused",
            }
        }
    )

    result = make_scanner(fake).scan_repository("o/svc")

    assert isinstance(result.repository, Service)
    assert result.error is None
    docs = {document.path: document for document in result.repository.documents}
    assert (
        docs["api-ref/source/bad.rst"].scan_result.failure_reason.code
        is IssueCode.FETCH_FAILED
    )
    assert isinstance(docs["api-ref/source/good.rst"], Endpoint)


def test_parser_crash_is_parser_error() -> None:
    """An unexpected parser exception is reported as parser_error, never as
    no_uri_match."""

    class CrashingParser(DocutilsParser):
        def parse(self, content: str, path: str, *, context=None):
            raise RuntimeError("boom")

    fake = FakeDocProvider(
        repos={"o/svc": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}}
    )
    scanner = make_scanner(fake, parser=CrashingParser())
    result = scanner.scan_repository("o/svc")
    assert isinstance(result.repository, Service)
    doc = result.repository.documents[0]
    assert doc.scan_result.failure_reason is not None
    assert doc.scan_result.failure_reason.code is IssueCode.PARSER_ERROR
    assert document_status(doc) == "failed"


def test_repository_context_failure_is_not_silently_ignored() -> None:
    class CrashingContextParser(DocutilsParser):
        def build_repository_context(self, documents):
            raise RuntimeError("broken shared schema")

    fake = FakeDocProvider(
        repos={"o/svc": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}}
    )

    result = make_scanner(fake, parser=CrashingContextParser()).scan_repository("o/svc")

    assert isinstance(result.repository, Service)
    assert result.repository.documents == []
    assert result.error == "Failed to build parser context: broken shared schema"


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
    result = scanner.scan_repository("o/svc")
    assert isinstance(result.repository, Service)
    doc = result.repository.documents[0]
    assert doc.title == "Some Endpoint"
    assert doc.scan_result.failure_reason is not None
    assert doc.scan_result.failure_reason.code is IssueCode.NO_URI_MATCH
    assert document_status(doc) == "failed"


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
    result = scanner.scan_repository("o/svc")
    assert isinstance(result.repository, Service)
    # Excluded file is not parsed, not counted as a non_endpoint doc...
    assert all(
        "out-of-date_apis" not in document.path
        for document in result.repository.documents
    )
    assert result.excluded_documents == ["api-ref/source/out-of-date_apis/old.rst"]


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
# Truncated tree → failed repo
# --------------------------------------------------------------------------- #
def test_scan_repository_fails_when_tree_is_truncated() -> None:
    """A capped file tree means the scanner never saw the complete pinned
    snapshot, so the whole repo scan must fail rather than silently continue
    with whatever the provider happened to return. The exact call list proves
    no content was fetched against that partial listing."""
    sha = "a" * 40
    fake = FakeDocProvider(
        repos={"o/svc": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}},
        truncated={"o/svc"},
        commit_hash=sha,
    )

    result = make_scanner(fake).scan_repository("o/svc")

    assert isinstance(result.repository, Service)
    assert result.repository.documents == []
    assert result.error
    assert fake.calls == [
        "get_commit_hash:o/svc@main",
        f"path_exists:o/svc@{sha}:api-ref/source",
        f"list_files:o/svc@{sha}",
    ]


# --------------------------------------------------------------------------- #
# API version analytics
# --------------------------------------------------------------------------- #
def test_api_version_is_carried_on_the_endpoint_not_a_parallel_field() -> None:
    """Version counts are derived by the panel from `Endpoint.api_version`,
    so the scanner must not store a second, drifting copy of them."""
    fake = FakeDocProvider(
        repos={
            "o/cce": {
                "api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst"),
            },
        }
    )

    result = make_scanner(fake).scan_repository("o/cce")

    assert "documents_by_version" not in RepositoryScanResult.model_fields
    endpoint = result.repository.documents[0]
    assert endpoint.api_version == "v3"


# --------------------------------------------------------------------------- #
# Scanner version stamped on the result
# --------------------------------------------------------------------------- #
def test_result_stamps_scanner_version() -> None:
    """Every result carries the scanner version that produced it, so consumers
    can tell "docs changed" apart from "parser improved"."""
    from tools import __version__

    fake = FakeDocProvider(
        repos={"o/cce": {"api-ref/source/x.rst": load_fixture("style_a_cce_grid.rst")}}
    )

    result = make_scanner(fake).scan_repository("o/cce")

    assert result.scanner_version == __version__
    # Present in the serialized JSON, not just the model.
    assert result.model_dump(mode="json")["scanner_version"] == __version__
