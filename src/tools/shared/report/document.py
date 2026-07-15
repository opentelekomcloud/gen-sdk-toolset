"""Per-document scan result form (data only).

Derived views — overall status, completeness, the flat issue list —
are computed by functions in ``tools.domain.report.analytics``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from tools.shared.ir import HttpMethod
from tools.shared.report.issue import Issue
from tools.shared.report.section import SectionScanResult


class DocumentScanResult(BaseModel):
    """Scan verdict + extracted data for one RST document.

    The model carries either a single gating ``failure_reason`` (no
    sections then) or per-section ``sections`` results (with possibly
    several issues across them).
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
    sections: dict[str, SectionScanResult] = Field(default_factory=dict)
