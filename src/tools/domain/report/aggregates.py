"""Repo- and org-level aggregates + the org-wide quality roll-up."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from tools import __version__ as _SCANNER_VERSION

from . import analytics
from .analytics import QualitySummary
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
        return analytics.count_documents(self.documents)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status_counts(self) -> dict[str, int]:
        """Distribution of overall_status across this repo's documents."""
        return analytics.count_by_status(self.documents)


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
        return analytics.count_by_version(self.repos)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def quality_summary(self) -> QualitySummary:
        """Compute the org-wide quality roll-up from per-doc results."""
        return analytics.compute_quality_summary(
            d for r in self.repos for d in r.documents
        )
