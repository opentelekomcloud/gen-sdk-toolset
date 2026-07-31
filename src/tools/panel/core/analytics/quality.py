"""Status vocabulary and per-document views shared by the panel's analytics.

Relocated from the deleted `tools.domain.report` with issue #34. Only the parts
:mod:`generation` builds on survived the move: the organization-level roll-ups
that used to live beside them (`QualitySummary`, `compute_quality_summary`,
`count_by_version`, `doc_overall_status`) were superseded by
:class:`~tools.panel.core.analytics.generation.GenerationAnalytics` and its
`document_status`, so keeping them would have left two definitions of one
number.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from tools.shared.ir import Document, Endpoint, Section

if TYPE_CHECKING:
    from tools.shared.scan import Issue

#: Bucket for an endpoint whose API version could not be read from its URI or
#: path. A real bucket, not an error.
UNVERSIONED_KEY = "unversioned"


class OverallStatus(StrEnum):
    """Document-level roll-up of gating and section results."""

    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


def document_sections(document: Document) -> list[Section]:
    """The sections of `document` that were actually scanned.

    Empty for a non-endpoint: only an `Endpoint` carries sections at all.
    """
    if not isinstance(document, Endpoint):
        return []
    return [section for section in document.sections if section.scan_result is not None]


def doc_all_issues(document: Document) -> list[Issue]:
    """Every diagnostic on `document`, flattened and located.

    Section-level issues are prefixed with the section they came from, so a
    flat list still says where each one was found.
    """
    issues: list[Issue] = []
    if document.scan_result is None:
        return issues
    if document.scan_result.failure_reason is not None:
        issues.append(document.scan_result.failure_reason)
    for section in document_sections(document):
        for issue in section.scan_result.issues:
            name = section.name.value
            location = f"{name}/{issue.location}" if issue.location else name
            issues.append(issue.model_copy(update={"location": location}))
    return issues
