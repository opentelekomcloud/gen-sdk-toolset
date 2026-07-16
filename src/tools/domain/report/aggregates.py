"""Org-level scan aggregate."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from tools import __version__ as _SCANNER_VERSION
from tools.shared.report import RepositoryScanResult

from . import analytics
from .analytics import QualitySummary

REPORT_SCHEMA_VERSION = 5


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
    repos: list[RepositoryScanResult] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_documents(self) -> int:
        return sum(
            analytics.count_documents(result.document_results) for result in self.repos
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def by_version(self) -> dict[str, int]:
        return analytics.count_by_version(self.repos)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def quality_summary(self) -> QualitySummary:
        """Compute the org-wide quality roll-up from per-doc results."""
        return analytics.compute_quality_summary(self.repos)
