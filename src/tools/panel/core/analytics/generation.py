"""Document- and generation-level roll-ups over one repository scan result.

Pure: no I/O, no clock, no database. :mod:`tools.panel.core.ingest` turns what
these functions return into the ``generation`` and ``document`` rows, so this is
the only place that decides what a persisted number means.

Two rules shape everything here:

* **Unknown is not zero.** A document whose structure could not be measured
  (a plain page, a gated document with no sections) gets ``None`` completeness,
  never ``0.0`` - the columns are nullable exactly for that.
* **Nothing is dropped to make a number look tidy.** Every document lands in one
  of the five status counters (the four :class:`OverallStatus` members plus
  ``unknown_count``), and every issue code is counted, not only the top ones.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, Field

# TODO(#34): these come from tools.domain.report, which issue #34 moves into
# this package. When that lands only these imports change - the roll-ups below
# are already in their final home.
from tools.domain.report.analytics import (
    _UNVERSIONED_KEY as UNVERSIONED_KEY,
)
from tools.domain.report.analytics import (
    _document_sections as document_sections,
)
from tools.domain.report.analytics import (
    doc_all_issues,
    doc_overall_status,
)
from tools.domain.report.enums import OverallStatus
from tools.shared.ir import Document, Endpoint
from tools.shared.scan import IssueCode

#: Diagnostics that describe **our** shortfall rather than the documentation's:
#: content we saw and could not read. They make a scan partial, and they must
#: not be counted against the documentation - the pages may be perfectly fine.
SCANNER_GAP_CODES = frozenset(
    {
        IssueCode.UNMAPPED_BLOCK,
        IssueCode.PARSER_ERROR,
        IssueCode.UNSUPPORTED_DOC_STYLE,
        IssueCode.FETCH_FAILED,
    }
)


class DocumentAnalytics(BaseModel):
    """Panel projections stored on one ``DocumentRecord``."""

    overall_status: OverallStatus | None = None
    completeness: float | None = None
    issues_count: int = 0


class GenerationAnalytics(BaseModel):
    """Everything one ``Generation`` row records about its documents.

    The counter fields map onto ``generation`` columns; the whole model is also
    stored as the ``analytics`` JSONB, so a reader gets the full picture -
    including the parts that have no column - from a single value. The row is
    immutable once ingested, so the two representations cannot drift apart.
    """

    documents_total: int = 0
    endpoints_total: int = 0
    non_endpoint_documents: int = 0
    issues_total: int = 0

    #: Documents carrying at least one diagnostic about the documentation.
    #: Their complement over the documents with a status is `docs_ok`.
    documentation_clean: int = 0
    #: Documents where something stayed unread - our gap, not the docs'.
    unread_documents: int = 0
    #: Documents we read end to end: nothing left unread and every documented
    #: parameter row recognized. The share of these is what "how well did the
    #: parser do" actually means - `completeness` only sees table rows and stays
    #: at 100% while whole sections go unread.
    read_in_full: int = 0

    ok_count: int = 0
    partial_count: int = 0
    failed_count: int = 0
    unsupported_count: int = 0
    #: Documents with no derivable status (a successfully scanned non-endpoint
    #: page). Without it the four status counters would not add up to
    #: documents_total and the difference would be unexplained.
    unknown_count: int = 0

    completeness: float | None = None
    fields_total: int = 0
    fields_recognized: int = 0

    by_section_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    issues_by_code: dict[str, int] = Field(default_factory=dict)
    by_version: dict[str, int] = Field(default_factory=dict)


def document_from_payload(payload: dict) -> Document:
    """Restore the canonical IR from a persisted ``DocumentRecord.payload``.

    The ``kind`` discriminator is what makes the subclass survive JSON, so the
    restoration lives here rather than at each read site.

    :param payload: The stored document payload.
    """
    if payload.get("kind") == "endpoint":
        return Endpoint.model_validate(payload)
    return Document.model_validate(payload)


def issues_by_code(document: Document) -> dict[str, int]:
    """Count one document's issues (document-level and section-level) by code.

    :param document: The scanned document IR to count.
    """
    counts: Counter[str] = Counter()
    for issue in doc_all_issues(document):
        counts[issue.code.value] += 1
    return dict(counts.most_common())


def document_field_totals(document: Document) -> tuple[int, int]:
    """Return ``(fields_total, fields_recognized)`` summed over the sections.

    :param document: The scanned document IR to measure.
    """
    total = 0
    recognized = 0
    for section in document_sections(document):
        total += section.scan_result.fields_total
        recognized += section.scan_result.fields_recognized
    return total, recognized


def doc_completeness(document: Document) -> float | None:
    """Return the recognized share of the documented parameter rows.

    ``None`` when nothing measurable was extracted - a non-endpoint page, or a
    document gated before any table was read. The section counters already
    reconcile (``recognized + unknown_type + failed == total``), so this is a
    measurement rather than an estimate.

    :param document: The scanned document IR to measure.
    """
    total, recognized = document_field_totals(document)
    if total == 0:
        return None
    return recognized / total


def is_unread(document: Document) -> bool:
    """True when a diagnostic says we could not read part of this document.

    :param document: The scanned document IR to inspect.
    """
    return any(issue.code in SCANNER_GAP_CODES for issue in doc_all_issues(document))


def has_documentation_defect(document: Document) -> bool:
    """True when a diagnostic describes the documentation itself.

    :param document: The scanned document IR to inspect.
    """
    return any(
        issue.code not in SCANNER_GAP_CODES for issue in doc_all_issues(document)
    )


def is_read_in_full(document: Document) -> bool:
    """True when nothing in this document was left unread.

    Two ways to fall short: content we saw and could not place (a scanner gap),
    and documented parameter rows we could not recognize. A document with no
    measurable rows at all cannot fail the second test - there was nothing to
    recognize.

    :param document: The scanned document IR to inspect.
    """
    if is_unread(document):
        return False
    completeness = doc_completeness(document)
    return completeness is None or completeness >= 1


def analyze_document(document: Document) -> DocumentAnalytics:
    """Return the panel projections for one scanned document.

    :param document: The scanned document IR to analyze.
    """
    return DocumentAnalytics(
        overall_status=doc_overall_status(document),
        completeness=doc_completeness(document),
        issues_count=len(doc_all_issues(document)),
    )


def analyze_generation(documents: Sequence[Document]) -> GenerationAnalytics:
    """Roll one scanned service's documents up into its ``Generation`` numbers.

    Walks the documents once. Generation completeness is field-weighted (the
    summed recognized rows over the summed documented rows), not a mean of
    per-document means: a one-row endpoint must not weigh as much as a
    fifty-row one.

    :param documents: Every document persisted with this generation.
    """
    status_counts: Counter[str] = Counter()
    section_counts: dict[str, Counter[str]] = {}
    issue_counts: Counter[str] = Counter()
    version_counts: Counter[str] = Counter()

    endpoints_total = 0
    issues_total = 0
    documentation_clean = 0
    unread_documents = 0
    read_in_full = 0
    fields_total = 0
    fields_recognized = 0

    for document in documents:
        status = doc_overall_status(document)
        status_counts[status.value if status is not None else "unknown"] += 1

        issues = doc_all_issues(document)
        issues_total += len(issues)
        if is_unread(document):
            unread_documents += 1
        if status is not None and is_read_in_full(document):
            read_in_full += 1
        if status is not None and not has_documentation_defect(document):
            # Every diagnostic here is about us, so as far as the documentation
            # goes this document came out clean.
            documentation_clean += 1
        for issue in issues:
            issue_counts[issue.code.value] += 1

        for section in document_sections(document):
            section_counts.setdefault(section.name.value, Counter())[
                section.scan_result.status.value
            ] += 1

        total, recognized = document_field_totals(document)
        fields_total += total
        fields_recognized += recognized

        if isinstance(document, Endpoint):
            endpoints_total += 1
            version_counts[document.api_version or UNVERSIONED_KEY] += 1

    documents_total = len(documents)
    return GenerationAnalytics(
        documents_total=documents_total,
        endpoints_total=endpoints_total,
        documentation_clean=documentation_clean,
        unread_documents=unread_documents,
        read_in_full=read_in_full,
        non_endpoint_documents=documents_total - endpoints_total,
        issues_total=issues_total,
        ok_count=status_counts[OverallStatus.OK.value],
        partial_count=status_counts[OverallStatus.PARTIAL.value],
        failed_count=status_counts[OverallStatus.FAILED.value],
        unsupported_count=status_counts[OverallStatus.UNSUPPORTED.value],
        unknown_count=status_counts["unknown"],
        completeness=(fields_recognized / fields_total) if fields_total else None,
        fields_total=fields_total,
        fields_recognized=fields_recognized,
        by_section_status={
            name: dict(counts) for name, counts in section_counts.items()
        },
        issues_by_code=dict(issue_counts),
        by_version=dict(version_counts.most_common()),
    )
