"""Repo- and org-level aggregates + the org-wide quality roll-up."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from pydantic import BaseModel, Field, computed_field

from tools import __version__ as _SCANNER_VERSION

from .document import DocumentScanResult

REPORT_SCHEMA_VERSION = 4


class RepoScanResult(BaseModel):
    """Aggregated scan result for one repository."""

    repo: str
    branch: str
    has_api_ref: bool = False

    # Version of the scanner/parser that produced this result, so report
    # diffing can tell "docs changed" from "parser improved" (addition A).
    scanner_version: str = _SCANNER_VERSION

    documents: list[DocumentScanResult] = Field(default_factory=list)

    # Files under api-ref/source/ that were *not* endpoint docs (intro
    # pages, conceptual material). Recorded here rather than dropped
    # silently so the inventory is honest.
    non_endpoint_documents: list[str] = Field(default_factory=list)

    # Files dropped before fetch because their path matched a configured
    # excluded segment (e.g. out-of-date_apis).
    excluded_documents: list[str] = Field(default_factory=list)

    # Successfully-or-partially extracted docs grouped by API version.
    # Failed / unsupported docs are *not* included here — they remain in
    # `documents`.
    documents_by_version: dict[str, list[DocumentScanResult]] = Field(
        default_factory=dict
    )

    # Set when the repo's file tree came back truncated from GitHub: the
    # scan saw only part of the files, so the result is not authoritative.
    incomplete: bool = False
    incomplete_reason: str | None = None

    # Set when the repo itself couldn't be scanned (e.g. tree fetch failed).
    error: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_documents(self) -> int:
        return len(self.documents)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status_counts(self) -> dict[str, int]:
        """Distribution of overall_status across this repo's documents."""
        return dict(Counter(d.overall_status.value for d in self.documents))


class QualitySummary(BaseModel):
    """Org-wide quality roll-up — drives Phase-3 Jinja-vs-LLM decisions."""

    by_overall_status: dict[str, int] = Field(default_factory=dict)
    # section_name → status → count, e.g. {"body": {"ok": 1200, "partial": 200}}.
    by_section_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    # Top issue codes across the entire org, by frequency.
    # Each entry: {"code": "<IssueCode.value>", "count": N}
    top_issues: list[dict] = Field(default_factory=list)


class OrgScanResult(BaseModel):
    """Top-level scan result for an organization."""

    report_schema_version: int = REPORT_SCHEMA_VERSION
    # Scanner/parser version that produced this report (addition A).
    scanner_version: str = _SCANNER_VERSION

    org: str
    branch: str
    total_repos: int = 0
    eligible_repos: int = 0
    skipped_repos: list[str] = Field(default_factory=list)
    repos: list[RepoScanResult] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_documents(self) -> int:
        return sum(r.total_documents for r in self.repos)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def by_version(self) -> dict[str, int]:
        """Org-wide count of parsed/partial documents per API version.

        Aggregated from each repo's ``documents_by_version`` so the fact
        lives in exactly one place. Ordered by descending count.
        """
        counts: Counter[str] = Counter()
        for repo in self.repos:
            for version, docs in repo.documents_by_version.items():
                counts[version] += len(docs)
        return dict(counts.most_common())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def quality_summary(self) -> QualitySummary:
        """Compute the org-wide quality roll-up from per-doc results."""
        return _compute_quality_summary(d for r in self.repos for d in r.documents)


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
_TOP_ISSUES_LIMIT = 20


def _compute_quality_summary(docs: Iterable[DocumentScanResult]) -> QualitySummary:
    by_overall: Counter[str] = Counter()
    by_section: dict[str, Counter[str]] = {}
    issue_counter: Counter[str] = Counter()

    for doc in docs:
        by_overall[doc.overall_status.value] += 1
        for section_name, section in doc.sections.items():
            by_section.setdefault(section_name, Counter())[section.status.value] += 1
        for iss in doc.all_issues:
            issue_counter[iss.code.value] += 1

    top = issue_counter.most_common(_TOP_ISSUES_LIMIT)
    return QualitySummary(
        by_overall_status=dict(by_overall),
        by_section_status={k: dict(v) for k, v in by_section.items()},
        top_issues=[{"code": code, "count": count} for code, count in top],
    )
