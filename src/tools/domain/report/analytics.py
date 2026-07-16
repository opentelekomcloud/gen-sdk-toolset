"""Pure counting and roll-up functions over scan results."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from tools.shared.ir import Endpoint, SectionName, Service
from tools.shared.report.enums import IssueCode, OverallStatus, SectionStatus
from tools.shared.report.keys import UNVERSIONED_KEY
from tools.shared.report.section import SectionScanResult

if TYPE_CHECKING:
    from tools.shared.report.document import DocumentScanResult
    from tools.shared.report.issue import Issue
    from tools.shared.report.repository import RepositoryScanResult

_TOP_ISSUES_LIMIT = 20
_SectionKey = tuple[str, SectionName]
_SectionResultIndex = Mapping[_SectionKey, SectionScanResult]


class QualitySummary(BaseModel):
    by_overall_status: dict[str, int] = Field(default_factory=dict)
    by_section_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    top_issues: list[dict] = Field(default_factory=list)


def _index_section_results(
    section_results: Iterable[SectionScanResult],
) -> dict[_SectionKey, SectionScanResult]:
    return {
        (result.section.endpoint_path, result.section.name): result
        for result in section_results
    }


def _document_section_results(
    doc: DocumentScanResult, section_results: _SectionResultIndex
) -> list[SectionScanResult]:
    if not isinstance(doc.document, Endpoint):
        return []
    return [
        section_results[(section.endpoint_path, section.name)]
        for section in doc.document.sections
        if (section.endpoint_path, section.name) in section_results
    ]


def _doc_overall_status(
    doc: DocumentScanResult, section_results: _SectionResultIndex
) -> OverallStatus:
    if doc.failure_reason is not None:
        if doc.failure_reason.code is IssueCode.UNSUPPORTED_DOC_STYLE:
            return OverallStatus.UNSUPPORTED
        return OverallStatus.FAILED

    degrading = {SectionStatus.PARTIAL, SectionStatus.FAILED, SectionStatus.SKIPPED}
    sections = _document_section_results(doc, section_results)
    if any(result.status in degrading for result in sections):
        return OverallStatus.PARTIAL
    return OverallStatus.OK


def doc_overall_status(
    doc: DocumentScanResult, section_results: Iterable[SectionScanResult]
) -> OverallStatus:
    return _doc_overall_status(doc, _index_section_results(section_results))


def doc_completeness(
    doc: DocumentScanResult, section_results: Iterable[SectionScanResult]
) -> float | None:
    if doc.failure_reason is not None:
        return None

    sections = _document_section_results(doc, _index_section_results(section_results))
    total = sum(result.fields_total for result in sections)
    if total > 0:
        recognized = sum(result.fields_recognized for result in sections)
        return recognized / total

    present = [
        result for result in sections if result.status is not SectionStatus.MISSING
    ]
    if not present:
        return None
    ok_count = sum(1 for result in present if result.status is SectionStatus.OK)
    return ok_count / len(present)


def _doc_all_issues(
    doc: DocumentScanResult, section_results: _SectionResultIndex
) -> list[Issue]:
    issues: list[Issue] = []
    if doc.failure_reason is not None:
        issues.append(doc.failure_reason)
    for result in _document_section_results(doc, section_results):
        for issue in result.issues:
            name = result.section.name
            location = f"{name}/{issue.location}" if issue.location else name
            issues.append(issue.model_copy(update={"location": location}))
    return issues


def doc_all_issues(
    doc: DocumentScanResult, section_results: Iterable[SectionScanResult]
) -> list[Issue]:
    return _doc_all_issues(doc, _index_section_results(section_results))


def count_documents(docs: Sequence[DocumentScanResult]) -> int:
    return len(docs)


def count_by_status(
    docs: Iterable[DocumentScanResult], section_results: Iterable[SectionScanResult]
) -> dict[str, int]:
    section_results_by_key = _index_section_results(section_results)
    return dict(
        Counter(_doc_overall_status(doc, section_results_by_key).value for doc in docs)
    )


def count_by_version(repos: Iterable[RepositoryScanResult]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for result in repos:
        if not isinstance(result.repository, Service):
            continue
        for endpoint in result.repository.endpoints:
            counts[endpoint.api_version or UNVERSIONED_KEY] += 1
    return dict(counts.most_common())


def compute_quality_summary(repos: Iterable[RepositoryScanResult]) -> QualitySummary:
    by_overall: Counter[str] = Counter()
    by_section: dict[str, Counter[str]] = {}
    issue_counter: Counter[str] = Counter()

    for repo in repos:
        section_results_by_key = _index_section_results(repo.section_results)
        for result in repo.section_results:
            by_section.setdefault(result.section.name.value, Counter())[
                result.status.value
            ] += 1

        for doc in repo.document_results:
            by_overall[_doc_overall_status(doc, section_results_by_key).value] += 1
            for issue in _doc_all_issues(doc, section_results_by_key):
                issue_counter[issue.code.value] += 1

    top = issue_counter.most_common(_TOP_ISSUES_LIMIT)
    return QualitySummary(
        by_overall_status=dict(by_overall),
        by_section_status={key: dict(value) for key, value in by_section.items()},
        top_issues=[{"code": code, "count": count} for code, count in top],
    )
