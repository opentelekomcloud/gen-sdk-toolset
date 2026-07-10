"""Per-document scan result + derived roll-ups."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from tools.shared.ir import HttpMethod
from tools.shared.report.enums import OverallStatus

from . import analytics
from .issue import Issue
from .section import SectionResult


class DocumentScanResult(BaseModel):
    """Scan verdict + extracted data for one RST document.

    The model carries either a single gating ``failure_reason`` (no
    sections then) or per-section ``sections`` results (with possibly
    several issues across them). The derived ``overall_status`` rolls
    these into one of ok / partial / failed / unsupported.
    """

    document: str
    repo: str

    # Gating data — populated only when gating succeeded.
    method: HttpMethod | None = None
    uri: str | None = None
    title: str | None = None
    api_version: str | None = None

    # At-most-one gating failure (gating is sequential, so multi-gating
    # failures are structurally impossible — see :class:`IssueCode`).
    failure_reason: Issue | None = None

    # Per-content-section results. Keys come from SECTION_NAMES. Sections
    # not present in the doc are omitted from the dict (their absence
    # equals SectionStatus.MISSING for accounting purposes).
    sections: dict[str, SectionResult] = Field(default_factory=dict)

    # ---------------- Derived (computed) views ---------------------- #
    @computed_field  # type: ignore[prop-decorator]
    @property
    def service(self) -> str:
        """Service slug derived from `repo` ("org/svc" → "svc")."""
        return analytics.doc_service(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def overall_status(self) -> OverallStatus:
        """Roll-up of gating + per-section results."""
        return analytics.doc_overall_status(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completeness(self) -> float | None:
        """0.0–1.0 measure of how much of the doc we extracted."""
        return analytics.doc_completeness(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_issues(self) -> list[Issue]:
        """Flat view of every issue affecting this doc, gating + content."""
        return analytics.doc_all_issues(self)
