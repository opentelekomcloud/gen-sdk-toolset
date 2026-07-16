from tools.domain.report import OrgScanResult
from tools.domain.report.analytics import doc_all_issues, doc_overall_status
from tools.shared.ir import (
    Document,
    Endpoint,
    HttpMethod,
    Section,
    SectionName,
    Service,
)
from tools.shared.report import (
    DocumentScanResult,
    Issue,
    IssueCode,
    RepositoryScanResult,
    SectionScanResult,
    SectionStatus,
)


def _repository_result(
    repo: str,
    body_status: SectionStatus,
    body_issues: list[Issue] | None = None,
) -> RepositoryScanResult:
    path = "api-ref/source/shared.rst"
    sections = [Section(endpoint_path=path, name=name) for name in SectionName]
    endpoint = Endpoint(
        path=path,
        method=HttpMethod.GET,
        uri="/v1/resources",
        sections=sections,
    )
    section_results = [
        SectionScanResult(
            section=section,
            status=(
                body_status
                if section.name is SectionName.BODY
                else SectionStatus.MISSING
            ),
            issues=body_issues or [] if section.name is SectionName.BODY else [],
        )
        for section in sections
    ]
    return RepositoryScanResult(
        repository=Service(repo=repo, documents=[endpoint]),
        branch="main",
        document_results=[DocumentScanResult(document=endpoint)],
        section_results=section_results,
    )


def test_quality_summary_keeps_same_document_paths_isolated_by_repository() -> None:
    result = OrgScanResult(
        org="example",
        branch="main",
        repos=[
            _repository_result("example/healthy", SectionStatus.OK),
            _repository_result(
                "example/degraded",
                SectionStatus.PARTIAL,
                [Issue(code=IssueCode.UNEXPECTED_COLUMNS)],
            ),
        ],
    )

    assert result.quality_summary.by_overall_status == {"ok": 1, "partial": 1}
    assert result.quality_summary.top_issues == [
        {"code": "unexpected_columns", "count": 1}
    ]


def test_doc_all_issues_prefixes_location_with_section_value() -> None:
    result = _repository_result(
        "example/service",
        SectionStatus.PARTIAL,
        [Issue(code=IssueCode.UNEXPECTED_COLUMNS, location="row 1")],
    )

    issues = doc_all_issues(result.document_results[0], result.section_results)

    assert issues[0].location == "body/row 1"


def test_non_endpoint_document_has_no_endpoint_quality_status() -> None:
    document = DocumentScanResult(document=Document(path="api-ref/source/intro.rst"))

    assert doc_overall_status(document, []) is None
