"""Pydantic request/response models for the panel API.

The read models are projections of what ingest already persisted: a Service
plus its active Snapshot and that snapshot's documents. Nothing here
recomputes a scan number - if a value is not in the database, it is derived by
:mod:`tools.panel.core.service_state`, never guessed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from tools.panel.core.analytics import document_from_payload, issues_by_code
from tools.panel.core.db.models import (
    DocumentRecord,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
    Snapshot,
)
from tools.panel.core.service_state import (
    RescanReason,
    ScanStatus,
    ServiceState,
    clean_endpoint_share,
    failed_job,
    read_in_full_share,
    status_documents,
)
from tools.shared.ir import Endpoint, SectionName

#: Every section name the UI renders, so a service scanned before a section
#: existed still gets the full strip instead of a ragged one.
_SECTION_NAMES = [name.value for name in SectionName]
_TOP_ISSUES_SHOWN = 10
#: Where a persisted document can be read in the original repository. Pinned to
#: the scanned commit, not to a branch: the page must show what was parsed, not
#: what the documentation looks like now.
_SOURCE_URL = "https://github.com/{repo}/blob/{commit}/{path}"


def source_url(*, repo: str, commit_hash: str, path: str) -> str:
    """Return the upstream URL of one scanned document."""
    return _SOURCE_URL.format(repo=repo, commit=commit_hash, path=path)


class ScanRequest(BaseModel):
    """Body for launching a scan: who initiated it."""

    initiated_by: str = Field(min_length=1)


class ExcludeRequest(BaseModel):
    """Body for excluding a service: why, and who decided.

    The reason is the entire audit record. Restoring a service deletes its
    exclusion row rather than archiving it, so this text is the only thing
    that ever explains why the service was hidden - a blank one is refused
    rather than stored as whitespace that reads as filled in.
    """

    reason: str = Field(min_length=1)
    initiated_by: str = Field(min_length=1)

    @field_validator("reason", "initiated_by")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class StartScanResponse(BaseModel):
    """Returned immediately when a scan Job is queued."""

    job_id: int


class JobResponse(BaseModel):
    """Job view for frontend polling (GET /api/jobs/{id})."""

    id: int
    service_id: int
    repository: str
    kind: JobKind
    status: JobStatus
    scanner_version: str | None
    commit_hash: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_job(cls, job: RepositoryScanJob) -> JobResponse:
        """Build the response from a Job.

        ``scanner_version`` and ``commit_hash`` come from the linked Snapshot,
        or None when the Job has no Snapshot.
        """
        snapshot = job.snapshot
        return cls(
            id=job.id,
            service_id=job.service_id,
            repository=job.service.repo,
            kind=job.kind,
            status=job.status,
            scanner_version=snapshot.scanner_version if snapshot else None,
            commit_hash=snapshot.commit_hash if snapshot else None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class IssueCount(BaseModel):
    """One issue code and how often it occurred."""

    code: str
    count: int


class SnapshotResponse(BaseModel):
    """One persisted scan snapshot (the `snapshot` row)."""

    id: int
    source_job_id: int
    branch: str
    commit_hash: str
    scanner_version: str
    document_schema_version: str
    documents_total: int
    endpoints_total: int
    non_endpoint_documents: int
    issues_total: int
    ok_count: int
    partial_count: int
    failed_count: int
    unsupported_count: int
    #: Documentation quality: percent of documents with no diagnostic at all.
    docs_ok: int | None
    #: Processing quality: percent of documents the scanner read end to end.
    #: Kept next to the first number so neither can be mistaken for the other.
    parser_ok: int | None
    #: The row-level detail behind parser_ok: the share of documented parameter
    #: rows that were recognized. Blind to content that was never read at all.
    completeness: float | None
    created_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot) -> SnapshotResponse:
        return cls(
            id=snapshot.id,
            source_job_id=snapshot.source_job_id,
            branch=snapshot.branch,
            commit_hash=snapshot.commit_hash,
            scanner_version=snapshot.scanner_version,
            document_schema_version=snapshot.document_schema_version,
            documents_total=snapshot.documents_total,
            endpoints_total=snapshot.endpoints_total,
            non_endpoint_documents=snapshot.non_endpoint_documents,
            issues_total=snapshot.issues_total,
            ok_count=snapshot.ok_count,
            partial_count=snapshot.partial_count,
            failed_count=snapshot.failed_count,
            unsupported_count=snapshot.unsupported_count,
            docs_ok=_docs_ok(snapshot),
            parser_ok=_parser_ok(snapshot),
            completeness=snapshot.completeness,
            created_at=snapshot.created_at,
        )


class SnapshotsResponse(BaseModel):
    """A service's snapshot history, newest first."""

    items: list[SnapshotResponse]
    active_id: int | None
    latest_id: int | None


class ServiceListItem(BaseModel):
    """One row of the registry, served from the service's active Snapshot.

    ``documents`` counts the documents that have a scan status, so it always
    equals the sum of ``overall_breakdown``. Pages that are not API documents
    are counted separately (see ``ServiceDetailResponse.non_endpoint_documents``)
    rather than folded into a status they do not have.
    """

    #: The identifier every route and link uses: Service.repo, always unique.
    name: str
    #: What the UI prints: Service.name, short enough to read in a table.
    label: str
    scan_status: ScanStatus
    documents: int | None
    #: Of those documents, the ones read end to end. The rest had content we
    #: could not read, so nothing about them is claimed with certainty.
    read_in_full: int | None
    #: Whole percent of documents scanned without a single diagnostic - the
    #: panel's measure of the documentation, not of the parser. The parser's
    #: own coverage lives on the snapshot as `completeness`.
    docs_ok: int | None
    scanner_version: str | None
    scanned_at: datetime | None
    docs_changed: bool
    rescan_reason: RescanReason | None
    overall_breakdown: dict[str, int]
    #: The part of each status bucket that was not read in full. The bar shows
    #: it grey, taken out of the colour rather than added on top of it.
    unread_breakdown: dict[str, int]
    #: Documents where something stayed unread. While this is above zero,
    #: `docs_ok` is an upper bound: defects can hide in what we did not read.
    unread_documents: int
    #: Documents read end to end whose parameter rows we could not all
    #: recognize. read_in_full + rows_unrecognized + unread_documents equals
    #: `documents`, so nothing is left unaccounted for.
    rows_unrecognized: int
    section_rollup: dict[str, dict[str, int]]
    error: str | None
    error_at: datetime | None
    job_id: int | None = None
    initiated_by: str | None = None
    started_at: datetime | None = None

    @classmethod
    def from_service(cls, service: Service, state: ServiceState) -> ServiceListItem:
        snapshot = state.active_snapshot
        failed = _failed_job(state)
        active_job = state.active_job
        return cls(
            name=service.repo,
            label=service.name,
            scan_status=state.scan_status,
            documents=_status_documents(snapshot),
            read_in_full=(
                _analytics(snapshot).get("read_in_full") if snapshot else None
            ),
            docs_ok=_docs_ok(snapshot),
            scanner_version=snapshot.scanner_version if snapshot else None,
            scanned_at=snapshot.created_at if snapshot else None,
            docs_changed=state.docs_changed,
            rescan_reason=state.rescan_reason,
            overall_breakdown=_overall_breakdown(snapshot),
            unread_breakdown=_analytics(snapshot).get("unread_by_status", {}),
            unread_documents=_analytics(snapshot).get("unread_documents", 0),
            rows_unrecognized=_analytics(snapshot).get("rows_unrecognized", 0),
            section_rollup=_section_rollup(snapshot),
            error=failed.error if failed else None,
            error_at=failed.finished_at if failed else None,
            job_id=active_job.id if active_job else None,
            initiated_by=active_job.initiated_by if active_job else None,
            started_at=active_job.started_at if active_job else None,
        )


class ServicesResponse(BaseModel):
    """The registry: matching rows plus the count behind every filter chip."""

    items: list[ServiceListItem]
    counts: dict[str, int]


class ServiceDetailResponse(ServiceListItem):
    """The service page: the registry row plus what only the detail view shows."""

    active_snapshot: SnapshotResponse | None
    latest_snapshot: SnapshotResponse | None
    head_commit: str | None
    interruption: dict[str, Any] | None
    top_issues: list[IssueCount]
    non_endpoint_documents: int

    @classmethod
    def from_service(
        cls, service: Service, state: ServiceState
    ) -> ServiceDetailResponse:
        row = ServiceListItem.from_service(service, state)
        snapshot = state.active_snapshot
        failed = _failed_job(state)
        return cls(
            **row.model_dump(),
            active_snapshot=(
                SnapshotResponse.from_snapshot(snapshot) if snapshot else None
            ),
            latest_snapshot=(
                SnapshotResponse.from_snapshot(state.latest_snapshot)
                if state.latest_snapshot
                else None
            ),
            head_commit=service.head_commit,
            interruption=failed.interruption if failed else None,
            top_issues=_top_issues(snapshot),
            non_endpoint_documents=_analytics(snapshot).get("unknown_count", 0),
        )


class DocumentListItem(BaseModel):
    """One row of the documents block."""

    id: int
    method: str | None
    uri: str | None
    title: str | None
    path: str
    overall_status: str
    issues: list[IssueCount]

    @classmethod
    def from_record(cls, record: DocumentRecord) -> DocumentListItem:
        return cls(
            id=record.id,
            method=record.method,
            uri=record.uri,
            title=record.title,
            path=record.path,
            overall_status=record.overall_status,
            issues=[
                IssueCount(code=code, count=count)
                for code, count in issues_by_code(
                    document_from_payload(record.payload)
                ).items()
            ],
        )


class DocumentsResponse(BaseModel):
    """One page of a snapshot's documents, with the counts behind the chips."""

    items: list[DocumentListItem]
    total: int
    page: int
    page_size: int
    doc_counts: dict[str, int]
    #: Matching documents per API version, `unversioned` for those that name
    #: none - the same key the snapshot analytics uses.
    version_counts: dict[str, int]


class ParameterResponse(BaseModel):
    """One parameter row, nested exactly as the scan recorded it."""

    name: str
    param_type: str
    mandatory: bool
    description: str
    children: list[ParameterResponse] | None = None


class ExampleResponse(BaseModel):
    """One request or response example, as written in the documentation.

    ``raw`` is the source text, shown verbatim: the point of an example is to
    compare it against what the parser made of it. Whether it was valid JSON is
    deliberately absent - not every example is JSON (a request line is a
    legitimate example), and the scanner already reports the real defect as an
    ``example_invalid_json`` issue on the section.
    """

    label: str | None
    language: str | None
    raw: str


class SectionDetail(BaseModel):
    """One endpoint section as the drill-down renders it."""

    name: str
    status: str
    fields_total: int
    fields_recognized: int
    fields_unknown_type: int
    parameters: list[ParameterResponse] | None
    issues: list[dict[str, str | None]]
    examples: list[ExampleResponse]


class DocumentDetailResponse(BaseModel):
    """The document drill-down: sections, parameters and diagnostics."""

    id: int
    method: str | None
    uri: str | None
    title: str | None
    api_version: str | None
    overall_status: str | None
    failure_reason: str | None
    #: The document in the repository, at the commit it was scanned from.
    source_url: str
    sections: list[SectionDetail]

    @classmethod
    def from_record(
        cls, record: DocumentRecord, *, repo: str, commit_hash: str
    ) -> DocumentDetailResponse:
        document = document_from_payload(record.payload)
        failure = document.scan_result.failure_reason if document.scan_result else None
        return cls(
            id=record.id,
            method=record.method,
            uri=record.uri,
            title=record.title,
            api_version=record.api_version,
            overall_status=record.overall_status,
            source_url=source_url(repo=repo, commit_hash=commit_hash, path=record.path),
            failure_reason=(
                f"{failure.code.value}: {failure.details}"
                if failure and failure.details
                else failure.code.value
                if failure
                else None
            ),
            sections=(
                [_section_detail(section) for section in document.sections]
                if isinstance(document, Endpoint)
                else []
            ),
        )


class SummaryResponse(BaseModel):
    """The header strip: one number per thing the panel is currently doing."""

    scanner_version: str
    last_scanned_at: datetime | None
    services_total: int
    failed_services: int
    documents_total: int
    scans_running: int


class AttentionRule(BaseModel):
    """One reason the panel is asking for attention, with how many services hit it."""

    code: str
    panel: str
    label: str
    count: int


class ExcludedServiceResponse(BaseModel):
    """One deliberately excluded service."""

    name: str
    reason: str
    excluded_by: str
    excluded_at: datetime


# ---------------------------------------------------------------------------
# Projections shared by the read models
# ---------------------------------------------------------------------------


def _failed_job(state: ServiceState) -> RepositoryScanJob | None:
    return failed_job(state)


def _analytics(snapshot: Snapshot | None) -> dict[str, Any]:
    return snapshot.analytics if snapshot is not None else {}


def _status_documents(snapshot: Snapshot | None) -> int | None:
    """Documents that carry a status - the denominator of the overall bar."""
    if snapshot is None:
        return None
    return status_documents(snapshot)


def _docs_ok(snapshot: Snapshot | None) -> int | None:
    """Clean-document share as whole percent; None stays None.

    Rounded **down**: 100% has to mean every document, not 99.6% of them. A
    percent that rounds up hides exactly the documents someone would go and
    look for.
    """
    if snapshot is None:
        return None
    share = clean_endpoint_share(snapshot)
    return None if share is None else int(share * 100)


def _parser_ok(snapshot: Snapshot | None) -> int | None:
    """Read-in-full share as whole percent, rounded down. None stays None."""
    if snapshot is None:
        return None
    share = read_in_full_share(snapshot)
    return None if share is None else int(share * 100)


def _overall_breakdown(snapshot: Snapshot | None) -> dict[str, int]:
    if snapshot is None:
        return {}
    return {
        "ok": snapshot.ok_count,
        "partial": snapshot.partial_count,
        "failed": snapshot.failed_count,
        "unsupported": snapshot.unsupported_count,
    }


def _section_rollup(snapshot: Snapshot | None) -> dict[str, dict[str, int]]:
    stored = _analytics(snapshot).get("by_section_status", {})
    return {name: stored.get(name, {}) for name in _SECTION_NAMES}


def _top_issues(snapshot: Snapshot | None) -> list[IssueCount]:
    """The loudest issue codes. The full map stays in the snapshot's analytics."""
    counts = _analytics(snapshot).get("issues_by_code", {})
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [
        IssueCount(code=code, count=count)
        for code, count in ordered[:_TOP_ISSUES_SHOWN]
    ]


def _section_detail(section: Any) -> SectionDetail:
    result = section.scan_result
    return SectionDetail(
        name=section.name.value,
        status=result.status.value if result else "missing",
        fields_total=result.fields_total if result else 0,
        fields_recognized=result.fields_recognized if result else 0,
        fields_unknown_type=result.fields_unknown_type if result else 0,
        parameters=(
            [_parameter(parameter) for parameter in section.parameters]
            if section.parameters
            else None
        ),
        issues=[
            {
                "code": issue.code.value,
                "location": issue.location,
                "details": issue.details,
            }
            for issue in (result.issues if result else [])
        ],
        examples=[
            ExampleResponse(
                label=example.label,
                language=example.language,
                raw=example.raw,
            )
            for example in section.examples
        ],
    )


def _parameter(parameter: Any) -> ParameterResponse:
    return ParameterResponse(
        name=parameter.name,
        param_type=parameter.param_type.value,
        mandatory=parameter.mandatory,
        description=parameter.description,
        children=(
            [_parameter(child) for child in parameter.children]
            if parameter.children
            else None
        ),
    )
