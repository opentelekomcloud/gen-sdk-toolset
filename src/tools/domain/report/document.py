"""Per-document scan result + derived roll-ups."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from tools.shared.ir import HttpMethod
from tools.shared.report.enums import IssueCode, OverallStatus, SectionStatus

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
        return self.repo.rsplit("/", 1)[-1]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def overall_status(self) -> OverallStatus:
        """Roll-up of gating + per-section results."""
        if self.failure_reason is not None:
            if self.failure_reason.code is IssueCode.UNSUPPORTED_DOC_STYLE:
                return OverallStatus.UNSUPPORTED
            return OverallStatus.FAILED
        # No gating failure → look at sections. MISSING is fine (legitimately
        # absent). Anything PARTIAL/FAILED degrades the doc to partial. SKIPPED
        # also degrades because it means we know there's something we didn't
        # parse.
        degrading = {SectionStatus.PARTIAL, SectionStatus.FAILED, SectionStatus.SKIPPED}
        if any(s.status in degrading for s in self.sections.values()):
            return OverallStatus.PARTIAL
        return OverallStatus.OK

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completeness(self) -> float | None:
        """0.0–1.0 measure of how much of the doc we extracted.

        Uses field-level metrics when they are populated (the parameter
        sections), falling back to section-level OK/total accounting
        when no field-level numbers are available.

        Returns ``None`` when gating failed — there's no meaningful
        completeness for a doc we couldn't even read.
        """
        if self.failure_reason is not None:
            return None

        # Prefer field-level when any section has populated counters.
        total = sum(s.fields_total for s in self.sections.values())
        if total > 0:
            recognized = sum(s.fields_recognized for s in self.sections.values())
            return recognized / total

        # Fall back to section status: OK / non-MISSING ratio.
        present = [
            s for s in self.sections.values() if s.status is not SectionStatus.MISSING
        ]
        if not present:
            return None
        ok_count = sum(1 for s in present if s.status is SectionStatus.OK)
        return ok_count / len(present)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_issues(self) -> list[Issue]:
        """Flat view of every issue affecting this doc, gating + content.

        Useful when you want "what's wrong with this doc?" in one list.
        Section context is preserved in each entry's `location` field.
        """
        out: list[Issue] = []
        if self.failure_reason is not None:
            out.append(self.failure_reason)
        for name, section in self.sections.items():
            for iss in section.issues:
                location = f"{name}/{iss.location}" if iss.location else name
                out.append(iss.model_copy(update={"location": location}))
        return out
