"""Per-document views shared by the panel's analytics.

The roll-ups these feed are covered by `test_document_analytics.py`; what is
pinned here is the two primitives `generation` builds on.
"""

from __future__ import annotations

from tools.panel.core.analytics.quality import doc_all_issues, document_sections
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


def _endpoint(body_issues: list[Issue] | None = None) -> Endpoint:
    sections = [
        Section(
            name=name,
            scan_result=SectionScanResult(
                status=(
                    SectionStatus.PARTIAL
                    if name is SectionName.BODY
                    else SectionStatus.MISSING
                ),
                issues=body_issues or [] if name is SectionName.BODY else [],
            ),
        )
        for name in SectionName
    ]
    return Endpoint(
        path="api-ref/source/shared.rst",
        method=HttpMethod.GET,
        uri="/v1/resources",
        sections=sections,
        scan_result=DocumentScanResult(),
    )


def test_doc_all_issues_prefixes_location_with_section_value() -> None:
    """A flattened issue must still say which section it came from, or the
    location it carries is ambiguous across the seven sections."""
    document = _endpoint([Issue(code=IssueCode.UNEXPECTED_COLUMNS, location="row 1")])

    issues = doc_all_issues(document)

    assert [issue.location for issue in issues] == ["body/row 1"]


def test_document_sections_is_empty_for_a_non_endpoint() -> None:
    """Only an Endpoint carries sections, so every caller that walks sections
    gets nothing for a plain page rather than an attribute error."""
    document = Document(
        path="api-ref/source/intro.rst",
        scan_result=DocumentScanResult(),
    )

    assert document_sections(document) == []
