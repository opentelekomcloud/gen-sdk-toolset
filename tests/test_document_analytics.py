"""Document- and generation-level roll-ups computed by the panel (issue #16).

Pure tests: no database, no fixtures on disk - the input is hand-built IR.
"""

from tools.panel.core.analytics import (
    analyze_document,
    analyze_generation,
    doc_completeness,
)
from tools.panel.core.analytics.generation import OverallStatus
from tools.shared.ir import (
    Document,
    Endpoint,
    HttpMethod,
    Section,
    SectionName,
)
from tools.shared.scan import (
    DocumentScanResult,
    Issue,
    IssueCode,
    SectionScanResult,
    SectionStatus,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _endpoint(
    path: str = "api-ref/source/create.rst",
    *,
    body: SectionScanResult | None = None,
    api_version: str | None = "v1",
) -> Endpoint:
    """An endpoint whose BODY carries the interesting result; the rest missing."""
    body = body or SectionScanResult(status=SectionStatus.OK)
    sections = [
        Section(
            name=name,
            scan_result=(
                body
                if name is SectionName.BODY
                else SectionScanResult(status=SectionStatus.MISSING)
            ),
        )
        for name in SectionName
    ]
    return Endpoint(
        path=path,
        title="Creating a Thing",
        method=HttpMethod.POST,
        uri="/v1/things",
        api_version=api_version,
        sections=sections,
        scan_result=DocumentScanResult(),
    )


def _plain(
    path: str = "api-ref/source/intro.rst", failure: Issue | None = None
) -> Document:
    return Document(
        path=path,
        title="Introduction",
        scan_result=DocumentScanResult(failure_reason=failure),
    )


def _measured_body(total: int, recognized: int) -> SectionScanResult:
    """A BODY result whose counters reconcile: the rest counts as failed."""
    return SectionScanResult(
        status=SectionStatus.OK if recognized == total else SectionStatus.PARTIAL,
        fields_total=total,
        fields_recognized=recognized,
        fields_failed=total - recognized,
    )


# ---------------------------------------------------------------------------
# Document status
# ---------------------------------------------------------------------------


def test_every_overall_status_is_reachable() -> None:
    """Reachability: a status nothing can produce is indistinguishable from a
    status that never happens."""
    produced = {
        analyze_document(document).overall_status
        for document in (
            _endpoint(),
            _endpoint(body=SectionScanResult(status=SectionStatus.PARTIAL)),
            _plain(failure=Issue(code=IssueCode.PARSER_ERROR)),
            _plain(failure=Issue(code=IssueCode.UNSUPPORTED_DOC_STYLE)),
        )
    }

    assert produced == set(OverallStatus)


def test_successfully_scanned_non_endpoint_has_no_status() -> None:
    """A page that is not an endpoint is not silently promoted to ``ok``."""
    assert analyze_document(_plain()).overall_status is None


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def test_completeness_is_the_recognized_share_of_documented_fields() -> None:
    endpoint = _endpoint(
        body=SectionScanResult(
            status=SectionStatus.PARTIAL,
            fields_total=8,
            fields_recognized=6,
            fields_unknown_type=1,
            fields_failed=1,
        )
    )

    assert doc_completeness(endpoint) == 0.75


def test_unmeasurable_completeness_is_none_not_zero() -> None:
    """Unknown and zero are different values: a document nobody could measure
    must not be reported as 0% structure."""
    assert doc_completeness(_plain()) is None
    assert doc_completeness(_plain(failure=Issue(code=IssueCode.PARSER_ERROR))) is None
    assert doc_completeness(_endpoint()) is None  # no field counters at all

    assert analyze_document(_plain()).completeness is None


def test_generation_completeness_is_field_weighted() -> None:
    """Weighted by fields, not a mean of per-document means: a one-row endpoint
    must not weigh as much as a three-row one (mean would say 0.5)."""
    analytics = analyze_generation(
        [
            _endpoint("a.rst", body=_measured_body(1, 1)),
            _endpoint("b.rst", body=_measured_body(3, 0)),
        ]
    )

    assert analytics.fields_total == 4
    assert analytics.fields_recognized == 1
    assert analytics.completeness == 0.25


def test_generation_completeness_is_none_without_measurable_fields() -> None:
    assert analyze_generation([_plain(), _endpoint()]).completeness is None


# ---------------------------------------------------------------------------
# Generation roll-up
# ---------------------------------------------------------------------------


def _mixed_documents() -> list[Document]:
    return [
        _endpoint("ok.rst", body=_measured_body(2, 2)),
        _endpoint("partial.rst", body=_measured_body(4, 3)),
        _plain("failed.rst", failure=Issue(code=IssueCode.PARSER_ERROR)),
        _plain("unsupported.rst", failure=Issue(code=IssueCode.UNSUPPORTED_DOC_STYLE)),
        _plain("intro.rst"),
    ]


def test_status_counters_account_for_every_document() -> None:
    """ok + partial + failed + unsupported + unknown == documents_total: a
    document that fits no status must still be counted somewhere."""
    analytics = analyze_generation(_mixed_documents())

    assert analytics.documents_total == 5
    assert (analytics.ok_count, analytics.partial_count) == (1, 1)
    assert (analytics.failed_count, analytics.unsupported_count) == (1, 1)
    assert analytics.unknown_count == 1
    assert (
        analytics.ok_count
        + analytics.partial_count
        + analytics.failed_count
        + analytics.unsupported_count
        + analytics.unknown_count
        == analytics.documents_total
    )


def test_document_counts_satisfy_the_generation_check_constraint() -> None:
    """endpoints_total + non_endpoint_documents = documents_total is a CHECK
    constraint on the generation table; assert it before the database does."""
    analytics = analyze_generation(_mixed_documents())

    assert analytics.endpoints_total == 2
    assert analytics.non_endpoint_documents == 3
    assert (
        analytics.endpoints_total + analytics.non_endpoint_documents
        == analytics.documents_total
    )


def test_issues_count_document_level_and_section_level() -> None:
    endpoint = _endpoint(
        "partial.rst",
        body=SectionScanResult(
            status=SectionStatus.PARTIAL,
            issues=[
                Issue(code=IssueCode.UNEXPECTED_COLUMNS, location="row 1"),
                Issue(code=IssueCode.UNKNOWN_TYPE_FORMAT, location="row 2"),
            ],
        ),
    )
    gated = _plain("gated.rst", failure=Issue(code=IssueCode.PARSER_ERROR))

    analytics = analyze_generation([endpoint, gated])

    assert analyze_document(endpoint).issues_count == 2
    assert analyze_document(gated).issues_count == 1
    assert analytics.issues_total == 3
    assert analytics.issues_by_code == {
        "unexpected_columns": 1,
        "unknown_type_format": 1,
        "parser_error": 1,
    }


def test_section_rollup_counts_every_section_of_every_endpoint() -> None:
    analytics = analyze_generation([_endpoint("a.rst"), _endpoint("b.rst")])

    assert analytics.by_section_status["body"] == {"ok": 2}
    assert analytics.by_section_status["response"] == {"missing": 2}
    assert set(analytics.by_section_status) == {name.value for name in SectionName}


def test_endpoints_without_api_version_land_in_the_unversioned_bucket() -> None:
    analytics = analyze_generation(
        [
            _endpoint("v1.rst", api_version="v1"),
            _endpoint("v2.rst", api_version="v2"),
            _endpoint("none.rst", api_version=None),
        ]
    )

    assert analytics.by_version == {"v1": 1, "v2": 1, "unversioned": 1}
    assert sum(analytics.by_version.values()) == analytics.endpoints_total


def test_empty_scan_produces_zeroed_analytics_with_unknown_completeness() -> None:
    analytics = analyze_generation([])

    assert analytics.documents_total == 0
    assert analytics.completeness is None
    assert analytics.issues_by_code == {}
