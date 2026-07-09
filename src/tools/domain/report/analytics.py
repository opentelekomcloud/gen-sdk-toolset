"""Pure counting/roll-up functions over the scan result forms.

Logic lives here, the forms stay data-only and delegate to these
functions.

Model types are needed only in annotations, so they are imported under
``TYPE_CHECKING`` — a runtime import would be circular (the model
modules import this one to delegate).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from tools.shared.report.enums import IssueCode, OverallStatus, SectionStatus

if TYPE_CHECKING:
    from tools.shared.report.document import DocumentScanResult
    from tools.shared.report.issue import Issue
    from tools.shared.report.repo import RepoScanResult

_TOP_ISSUES_LIMIT = 20


class QualitySummary(BaseModel):
    """Org-wide quality roll-up — drives Phase-3 Jinja-vs-LLM decisions."""

    by_overall_status: dict[str, int] = Field(default_factory=dict)
    # section_name → status → count, e.g. {"body": {"ok": 1200, "partial": 200}}.
    by_section_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    # Top issue codes across the entire org, by frequency.
    # Each entry: {"code": "<IssueCode.value>", "count": N}
    top_issues: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Per-document analytics
# --------------------------------------------------------------------------- #
def doc_service(doc: DocumentScanResult) -> str:
    """Service slug derived from `repo` ("org/svc" → "svc")."""
    return doc.repo.rsplit("/", 1)[-1]


def doc_overall_status(doc: DocumentScanResult) -> OverallStatus:
    """Roll-up of gating + per-section results."""
    if doc.failure_reason is not None:
        if doc.failure_reason.code is IssueCode.UNSUPPORTED_DOC_STYLE:
            return OverallStatus.UNSUPPORTED
        return OverallStatus.FAILED
    # No gating failure → look at sections. MISSING is fine (legitimately
    # absent). Anything PARTIAL/FAILED degrades the doc to partial. SKIPPED
    # also degrades because it means we know there's something we didn't
    # parse.
    degrading = {SectionStatus.PARTIAL, SectionStatus.FAILED, SectionStatus.SKIPPED}
    if any(s.status in degrading for s in doc.sections.values()):
        return OverallStatus.PARTIAL
    return OverallStatus.OK


def doc_completeness(doc: DocumentScanResult) -> float | None:
    """0.0–1.0 measure of how much of the doc we extracted.

    Uses field-level metrics when they are populated (the parameter
    sections), falling back to section-level OK/total accounting
    when no field-level numbers are available.

    Returns ``None`` when gating failed — there's no meaningful
    completeness for a doc we couldn't even read.
    """
    if doc.failure_reason is not None:
        return None

    # Prefer field-level when any section has populated counters.
    total = sum(s.fields_total for s in doc.sections.values())
    if total > 0:
        recognized = sum(s.fields_recognized for s in doc.sections.values())
        return recognized / total

    # Fall back to section status: OK / non-MISSING ratio.
    present = [
        s for s in doc.sections.values() if s.status is not SectionStatus.MISSING
    ]
    if not present:
        return None
    ok_count = sum(1 for s in present if s.status is SectionStatus.OK)
    return ok_count / len(present)


def doc_all_issues(doc: DocumentScanResult) -> list[Issue]:
    """Flat view of every issue affecting this doc, gating + content.

    Useful when you want "what's wrong with this doc?" in one list.
    Section context is preserved in each entry's `location` field.
    """
    out: list[Issue] = []
    if doc.failure_reason is not None:
        out.append(doc.failure_reason)
    for name, section in doc.sections.items():
        for iss in section.issues:
            location = f"{name}/{iss.location}" if iss.location else name
            out.append(iss.model_copy(update={"location": location}))
    return out


# --------------------------------------------------------------------------- #
# Collection analytics
# --------------------------------------------------------------------------- #
def count_documents(docs: Sequence[DocumentScanResult]) -> int:
    return len(docs)


def count_by_status(docs: Iterable[DocumentScanResult]) -> dict[str, int]:
    """Distribution of overall_status across the given documents."""
    return dict(Counter(doc_overall_status(d).value for d in docs))


def count_by_version(repos: Iterable[RepoScanResult]) -> dict[str, int]:
    """Count of parsed/partial documents per API version.

    Aggregated from each repo's ``documents_by_version`` so the fact
    lives in exactly one place. Ordered by descending count.
    """
    counts: Counter[str] = Counter()
    for repo in repos:
        for version, docs in repo.documents_by_version.items():
            counts[version] += len(docs)
    return dict(counts.most_common())


def compute_quality_summary(docs: Iterable[DocumentScanResult]) -> QualitySummary:
    """Compute the org-wide quality roll-up from per-doc results."""
    by_overall: Counter[str] = Counter()
    by_section: dict[str, Counter[str]] = {}
    issue_counter: Counter[str] = Counter()

    for doc in docs:
        by_overall[doc_overall_status(doc).value] += 1
        for section_name, section in doc.sections.items():
            by_section.setdefault(section_name, Counter())[section.status.value] += 1
        for iss in doc_all_issues(doc):
            issue_counter[iss.code.value] += 1

    top = issue_counter.most_common(_TOP_ISSUES_LIMIT)
    return QualitySummary(
        by_overall_status=dict(by_overall),
        by_section_status={k: dict(v) for k, v in by_section.items()},
        top_issues=[{"code": code, "count": count} for code, count in top],
    )
