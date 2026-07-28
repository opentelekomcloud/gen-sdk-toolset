"""Pydantic request/response models for the panel API.

The read models are projections of what ingest already persisted: a Service
plus its active Generation and that generation's documents. Nothing here
recomputes a scan number - if a value is not in the database, it is derived by
:mod:`tools.panel.core.service_state`, never guessed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from tools.panel.core.analytics import document_from_payload, issues_by_code
from tools.panel.core.db.models import (
    DocumentRecord,
    Generation,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
)
from tools.panel.core.service_state import (
    RescanReason,
    ScanStatus,
    ServiceState,
    clean_endpoint_share,
    failed_job,
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

        ``scanner_version`` and ``commit_hash`` come from the linked Generation,
        or None when the Job has no Generation.
        """
        generation = job.generation
        return cls(
            id=job.id,
            service_id=job.service_id,
            repository=job.service.repo,
            kind=job.kind,
            status=job.status,
            scanner_version=generation.scanner_version if generation else None,
            commit_hash=generation.commit_hash if generation else None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class IssueCount(BaseModel):
    """One issue code and how often it occurred."""

    code: str
    count: int


class GenerationResponse(BaseModel):
    """One persisted scan snapshot (the `generation` row)."""

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
    #: Processing quality: the share of documented parameter rows the parser
    #: understood. A different question, kept next to the first one so neither
    #: can be mistaken for the other.
    completeness: float | None
    created_at: datetime

    @classmethod
    def from_generation(cls, generation: Generation) -> GenerationResponse:
        return cls(
            id=generation.id,
            source_job_id=generation.source_job_id,
            branch=generation.branch,
            commit_hash=generation.commit_hash,
            scanner_version=generation.scanner_version,
            document_schema_version=generation.document_schema_version,
            documents_total=generation.documents_total,
            endpoints_total=generation.endpoints_total,
            non_endpoint_documents=generation.non_endpoint_documents,
            issues_total=generation.issues_total,
            ok_count=generation.ok_count,
            partial_count=generation.partial_count,
            failed_count=generation.failed_count,
            unsupported_count=generation.unsupported_count,
            docs_ok=_docs_ok(generation),
            completeness=generation.completeness,
            created_at=generation.created_at,
        )


class GenerationsResponse(BaseModel):
    """A service's generation history, newest first."""

    items: list[GenerationResponse]
    active_id: int | None
    latest_id: int | None


class ServiceListItem(BaseModel):
    """One row of the registry, served from the service's active Generation.

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
    #: Whole percent of documents scanned without a single diagnostic - the
    #: panel's measure of the documentation, not of the parser. The parser's
    #: own coverage lives on the generation as `completeness`.
    docs_ok: int | None
    scanner_version: str | None
    scanned_at: datetime | None
    docs_changed: bool
    rescan_reason: RescanReason | None
    overall_breakdown: dict[str, int]
    section_rollup: dict[str, dict[str, int]]
    error: str | None
    error_at: datetime | None
    job_id: int | None = None
    initiated_by: str | None = None
    started_at: datetime | None = None

    @classmethod
    def from_service(cls, service: Service, state: ServiceState) -> ServiceListItem:
        generation = state.active_generation
        failed = _failed_job(state)
        active_job = state.active_job
        return cls(
            name=service.repo,
            label=service.name,
            scan_status=state.scan_status,
            documents=_status_documents(generation),
            docs_ok=_docs_ok(generation),
            scanner_version=generation.scanner_version if generation else None,
            scanned_at=generation.created_at if generation else None,
            docs_changed=state.docs_changed,
            rescan_reason=state.rescan_reason,
            overall_breakdown=_overall_breakdown(generation),
            section_rollup=_section_rollup(generation),
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

    active_generation: GenerationResponse | None
    latest_generation: GenerationResponse | None
    head_commit: str | None
    interruption: dict[str, Any] | None
    top_issues: list[IssueCount]
    non_endpoint_documents: int

    @classmethod
    def from_service(
        cls, service: Service, state: ServiceState
    ) -> ServiceDetailResponse:
        row = ServiceListItem.from_service(service, state)
        generation = state.active_generation
        failed = _failed_job(state)
        return cls(
            **row.model_dump(),
            active_generation=(
                GenerationResponse.from_generation(generation) if generation else None
            ),
            latest_generation=(
                GenerationResponse.from_generation(state.latest_generation)
                if state.latest_generation
                else None
            ),
            head_commit=service.head_commit,
            interruption=failed.interruption if failed else None,
            top_issues=_top_issues(generation),
            non_endpoint_documents=_analytics(generation).get("unknown_count", 0),
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
    """One page of a generation's documents, with the counts behind the chips."""

    items: list[DocumentListItem]
    total: int
    page: int
    page_size: int
    doc_counts: dict[str, int]


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


def _analytics(generation: Generation | None) -> dict[str, Any]:
    return generation.analytics if generation is not None else {}


def _status_documents(generation: Generation | None) -> int | None:
    """Documents that carry a status - the denominator of the overall bar."""
    if generation is None:
        return None
    return status_documents(generation)


def _docs_ok(generation: Generation | None) -> int | None:
    """Clean-document share as whole percent; None stays None.

    Rounded **down**: 100% has to mean every document, not 99.6% of them. A
    percent that rounds up hides exactly the documents someone would go and
    look for.
    """
    if generation is None:
        return None
    share = clean_endpoint_share(generation)
    return None if share is None else int(share * 100)


def _overall_breakdown(generation: Generation | None) -> dict[str, int]:
    if generation is None:
        return {}
    return {
        "ok": generation.ok_count,
        "partial": generation.partial_count,
        "failed": generation.failed_count,
        "unsupported": generation.unsupported_count,
    }


def _section_rollup(generation: Generation | None) -> dict[str, dict[str, int]]:
    stored = _analytics(generation).get("by_section_status", {})
    return {name: stored.get(name, {}) for name in _SECTION_NAMES}


def _top_issues(generation: Generation | None) -> list[IssueCount]:
    """The loudest issue codes. The full map stays in the generation's analytics."""
    counts = _analytics(generation).get("issues_by_code", {})
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
