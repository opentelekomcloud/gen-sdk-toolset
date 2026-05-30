"""Quality-report scan result models.

Designed around two ideas that came out of the issue-#5 discussion:

* **Gating vs content.** Parsing a doc has prerequisite steps (fetch the
  file, recognise it as an endpoint doc, locate the URI) and content
  steps (extract path / query / body / response parameters, examples,
  nested objects). A failure in a gating step makes the doc unusable;
  a failure in one content section is independent of the others, so the
  doc can still be *partially* useful.
* **Per-section result + structured issues.** Every content section
  carries its own :class:`SectionStatus`, structured :class:`Issue`
  entries, the actually-extracted data (``parameters`` / ``examples``),
  and field-level metrics. The data and the metrics travel together —
  no parallel storage to keep in sync.

The org-wide report (:class:`OrgScanResult`) carries a derived
:class:`QualitySummary` so a single JSON dump answers "how is the doc
set doing across all repos".
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from .ir import HttpMethod, Parameter

REPORT_SCHEMA_VERSION = 1

# --------------------------------------------------------------------------- #
# Section identifiers
# --------------------------------------------------------------------------- #
# Canonical section names. Used as keys in DocumentScanResult.sections so the
# JSON output has a stable shape regardless of which sections a given doc
# actually contains.
#
# `nested_objects` is reserved for the upcoming ref-resolution work (#6) —
# defined here so the model schema stays stable across PRs.
SECTION_NAMES: tuple[str, ...] = (
    "path_params",
    "query_params",
    "headers",
    "body",
    "response",
    "example_request",
    "example_response",
    "nested_objects",
)


class SectionStatus(str, Enum):
    """How well we extracted one section of a doc."""

    OK = "ok"  # fully extracted, no issues
    PARTIAL = "partial"  # extracted with one or more issues
    FAILED = "failed"  # section present in doc but extraction failed
    MISSING = "missing"  # section legitimately absent (e.g. GET with no body)
    SKIPPED = "skipped"  # parser doesn't handle this section in this doc


class IssueCode(str, Enum):
    """Structured codes for things that can go wrong during scanning."""

    # --- Gating (at most one per doc, in DocumentScanResult.failure_reason)
    FETCH_FAILED = "fetch_failed"
    NOT_AN_ENDPOINT_DOC = "not_an_endpoint_doc"
    NO_URI_MATCH = "no_uri_match"
    UNSUPPORTED_DOC_STYLE = "unsupported_doc_style"

    # --- Structural / table-level (in SectionResult.issues)
    TABLE_NOT_FOUND = "table_not_found"
    MALFORMED_GRID_TABLE = "malformed_grid_table"
    UNEXPECTED_COLUMNS = "unexpected_columns"

    # --- Field-level (in SectionResult.issues, with location="row N")
    UNKNOWN_TYPE_FORMAT = "unknown_type_format"
    EMPTY_MANDATORY_COLUMN = "empty_mandatory_column"
    DESCRIPTION_TRUNCATED = "description_truncated"

    # --- Nested resolution (#6 — defined now so the enum is stable later)
    NESTED_TABLE_NOT_FOUND = "nested_table_not_found"
    NESTED_CIRCULAR_REF = "nested_circular_ref"

    # --- Examples
    EXAMPLE_INVALID_JSON = "example_invalid_json"
    EXAMPLE_MISSING = "example_missing"
    EXAMPLE_LLM_FAILED = "example_llm_failed"  # reserved for later LLM-assisted parsing


class Issue(BaseModel):
    """A single problem encountered while processing a doc.

    `code` is queryable; `location` gives a human breadcrumb
    (e.g. "Table 3" or "row 5"); `details` carries free-text context
    that isn't structured but is invaluable when debugging.
    """

    code: IssueCode
    location: str | None = None
    details: str | None = None


# --------------------------------------------------------------------------- #
# Per-section data: extracted content + metrics
# --------------------------------------------------------------------------- #
class ExampleBlock(BaseModel):
    """One example code block (request or response).

    Stored as both raw text and best-effort parsed JSON. `parsed` is
    ``None`` whenever the code block isn't valid JSON — many OTC examples
    are wire-format HTTP, cURL fragments, or JSON with stray comments.
    """

    raw: str
    language: str | None = None
    parsed: dict | list | None = None
    label: str | None = None  # e.g. "Specifying versionId to Delete a Specific Version"


class SectionResult(BaseModel):
    """Result of attempting to extract one content section of a doc.

    Carries both the extracted data (``parameters`` / ``examples``) and
    the quality metrics. The two live together so consumers don't have
    to join across separate stores.
    """

    status: SectionStatus
    issues: list[Issue] = Field(default_factory=list)

    # Extracted content. Empty for sections that are MISSING / SKIPPED /
    # not parameter-bearing (e.g. example_* sections use `examples`).
    parameters: list[Parameter] = Field(default_factory=list)
    examples: list[ExampleBlock] = Field(default_factory=list)

    # Field-level metrics. Defined as:
    #   fields_total       — number of rows in the table(s) we walked
    #   fields_recognized  — rows with a non-empty name AND a non-empty type cell
    #   fields_unknown_type — rows with a name but a type we couldn't classify
    #   fields_failed      — rows we couldn't parse at all
    # (fields_recognized + fields_unknown_type + fields_failed) == fields_total
    fields_total: int = 0
    fields_recognized: int = 0
    fields_unknown_type: int = 0
    fields_failed: int = 0


# --------------------------------------------------------------------------- #
# Parser → scanner: what the parser hands back
# --------------------------------------------------------------------------- #
class ParsedDocument(BaseModel):
    """Parser output for one Style-A doc.

    The parser is style-agnostic at its public surface: callers pass an
    RST string, get back this object on success or a ``ParseFailure``
    exception on a gating problem. Style classification happens at the
    scanner layer, *before* the parser is invoked.
    """

    method: HttpMethod
    uri: str
    title: str | None = None
    api_version: str | None = None
    sections: dict[str, SectionResult] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Scanner output: per-document, per-repo, per-org
# --------------------------------------------------------------------------- #
OverallStatus = Literal["ok", "partial", "failed", "unsupported"]


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
                return "unsupported"
            return "failed"
        # No gating failure → look at sections. MISSING is fine (legitimately
        # absent). Anything PARTIAL/FAILED degrades the doc to partial. SKIPPED
        # also degrades because it means we know there's something we didn't
        # parse.
        degrading = {SectionStatus.PARTIAL, SectionStatus.FAILED, SectionStatus.SKIPPED}
        if any(s.status in degrading for s in self.sections.values()):
            return "partial"
        return "ok"

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


class RepoScanResult(BaseModel):
    """Aggregated scan result for one repository."""

    repo: str
    branch: str
    has_api_ref: bool = False

    documents: list[DocumentScanResult] = Field(default_factory=list)

    # Files under api-ref/source/ that were *not* endpoint docs (intro
    # pages, conceptual material). Recorded here rather than dropped
    # silently so the inventory is honest.
    non_endpoint_documents: list[str] = Field(default_factory=list)

    # Successfully-or-partially extracted docs grouped by API version.
    # Failed / unsupported docs are *not* included here — they remain in
    # `documents`.
    documents_by_version: dict[str, list[DocumentScanResult]] = Field(
        default_factory=dict
    )

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
        return dict(Counter(d.overall_status for d in self.documents))


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
        by_overall[doc.overall_status] += 1
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


# --------------------------------------------------------------------------- #
# Parser failure signal
# --------------------------------------------------------------------------- #
class ParseFailure(Exception):
    """Raised by the parser when a gating step fails (e.g. no URI in doc).

    Caught at the scanner layer and converted into
    :attr:`DocumentScanResult.failure_reason`.
    """

    def __init__(self, code: IssueCode, details: str | None = None):
        self.issue = Issue(code=code, details=details)
        super().__init__(f"{code.value}" + (f": {details}" if details else ""))
