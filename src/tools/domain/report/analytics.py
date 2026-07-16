"""Pure counting and roll-up functions over nested scan results."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from tools.shared.ir import Document, Endpoint, Section, Service
from tools.shared.scan import IssueCode, SectionStatus

if TYPE_CHECKING:
    from tools.shared.scan import Issue, RepositoryScanResult

from .enums import OverallStatus

_TOP_ISSUES_LIMIT = 20
_UNVERSIONED_KEY = "unversioned"


class QualitySummary(BaseModel):
    by_overall_status: dict[str, int] = Field(default_factory=dict)
    by_section_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    top_issues: list[dict] = Field(default_factory=list)


def _document_sections(document: Document) -> list[Section]:
    if not isinstance(document, Endpoint):
        return []
    return [section for section in document.sections if section.scan_result is not None]


def doc_overall_status(document: Document) -> OverallStatus | None:
    if document.scan_result is None:
        return None
    failure = document.scan_result.failure_reason
    if failure is not None:
        if failure.code is IssueCode.UNSUPPORTED_DOC_STYLE:
            return OverallStatus.UNSUPPORTED
        return OverallStatus.FAILED
    if not isinstance(document, Endpoint):
        return None

    degrading = {SectionStatus.PARTIAL, SectionStatus.FAILED, SectionStatus.SKIPPED}
    if any(
        section.scan_result.status in degrading
        for section in _document_sections(document)
    ):
        return OverallStatus.PARTIAL
    return OverallStatus.OK


def doc_all_issues(document: Document) -> list[Issue]:
    issues: list[Issue] = []
    if document.scan_result is None:
        return issues
    if document.scan_result.failure_reason is not None:
        issues.append(document.scan_result.failure_reason)
    for section in _document_sections(document):
        for issue in section.scan_result.issues:
            name = section.name.value
            location = f"{name}/{issue.location}" if issue.location else name
            issues.append(issue.model_copy(update={"location": location}))
    return issues


def count_documents(documents: Sequence[Document]) -> int:
    return len(documents)


def count_by_version(repos: Iterable[RepositoryScanResult]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for result in repos:
        if not isinstance(result.repository, Service):
            continue
        for endpoint in result.repository.endpoints:
            counts[endpoint.api_version or _UNVERSIONED_KEY] += 1
    return dict(counts.most_common())


def compute_quality_summary(repos: Iterable[RepositoryScanResult]) -> QualitySummary:
    by_overall: Counter[str] = Counter()
    by_section: dict[str, Counter[str]] = {}
    issue_counter: Counter[str] = Counter()

    for repo in repos:
        if not isinstance(repo.repository, Service):
            continue
        for document in repo.repository.documents:
            for section in _document_sections(document):
                by_section.setdefault(section.name.value, Counter())[
                    section.scan_result.status.value
                ] += 1

            status = doc_overall_status(document)
            if status is not None:
                by_overall[status.value] += 1
            for issue in doc_all_issues(document):
                issue_counter[issue.code.value] += 1

    top = issue_counter.most_common(_TOP_ISSUES_LIMIT)
    return QualitySummary(
        by_overall_status=dict(by_overall),
        by_section_status={key: dict(value) for key, value in by_section.items()},
        top_issues=[{"code": code, "count": count} for code, count in top],
    )
