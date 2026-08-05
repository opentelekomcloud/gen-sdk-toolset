"""Read endpoints: what the panel shows about scanned services.

Every value served here was produced by ingest and stored - these routes
project, filter and paginate, they never rescan and never call GitHub. Filters
and ordering that depend on the derived service state (scanning, needs_rescan,
quality) are applied in Python over the loaded rows: the registry is dozens of
services, and one source of truth for "what partial means"
(:mod:`tools.panel.core.service_state`) is worth more than a clever query.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session, joinedload, selectinload, undefer

from tools import __version__ as SCANNER_VERSION
from tools.panel.api.deps import get_db
from tools.panel.api.schemas import (
    AttentionRule,
    DocumentDetailResponse,
    DocumentListItem,
    DocumentsResponse,
    ExcludedServiceResponse,
    ServiceDetailResponse,
    ServiceListItem,
    ServicesResponse,
    SnapshotResponse,
    SnapshotsResponse,
    SummaryResponse,
)
from tools.panel.core.analytics import document_from_payload
from tools.panel.core.analytics.snapshot import UNVERSIONED_KEY as UNVERSIONED
from tools.panel.core.db.models import (
    DocumentRecord,
    ExcludedService,
    Service,
    Snapshot,
)
from tools.panel.core.service_state import (
    ScanStatus,
    ServiceState,
    derive_service_state,
    failed_job,
    status_documents,
)
from tools.shared.ir import Service as IrService
from tools.shared.scan import RepositoryScanResult

router = APIRouter()

PAGE_SIZE = 20

#: Filter chips on the registry, in the order the UI renders them.
SERVICE_FILTERS = ("all", *(status.value for status in ScanStatus), "needs_rescan")

#: Worst first: the documents that need a human come at the top of the list.
_STATUS_ORDER = case(
    {"failed": 0, "partial": 1, "unsupported": 2, "ok": 3},
    value=DocumentRecord.overall_status,
    else_=4,
)

#: "which documents have a failed body?" - answered against the stored payload,
#: so no section projection has to be denormalized into its own column.
_SECTION_MATCH = "$.sections[*] ? (@.name == $name && @.scan_result.status == $status)"

#: "which documents raised this issue?" - `code` appears only on an Issue, at
#: section level or on the gating failure, so one recursive match covers both.
_ISSUE_MATCH = "$.**.code ? (@ == $code)"

_ATTENTION_LABELS = {
    "failed": "Last scan failed",
    "version": "Scanned by an older scanner",
    "drift": "Documentation moved ahead",
    "new": "Never scanned",
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@router.get("/scan/summary", response_model=SummaryResponse)
def get_summary(db: Session = Depends(get_db)) -> SummaryResponse:
    """Panel-wide counters for the header strip."""
    states = _all_states(db)
    scanned = [state for state in states if state.active_snapshot is not None]
    return SummaryResponse(
        scanner_version=SCANNER_VERSION,
        last_scanned_at=max(
            (state.active_snapshot.created_at for state in scanned), default=None
        ),
        services_total=len(states),
        failed_services=sum(failed_job(state) is not None for state in states),
        documents_total=sum(
            status_documents(state.active_snapshot) for state in scanned
        ),
        scans_running=sum(state.active_job is not None for state in states),
    )


@router.get("/scan/attention", response_model=list[AttentionRule])
def get_attention(db: Session = Depends(get_db)) -> list[AttentionRule]:
    """Reasons the panel wants attention, with the number of services behind each.

    The predicates are independent, unlike ``rescan_reason``: a service whose
    documents are partial *and* whose scanner is outdated is counted under both
    rules, because hiding one behind the other would understate the work.
    """
    states = _all_states(db)
    counts = {
        "failed": sum(failed_job(state) is not None for state in states),
        "version": sum(
            state.active_snapshot is not None
            and state.active_snapshot.scanner_version != SCANNER_VERSION
            for state in states
        ),
        "drift": sum(state.docs_changed for state in states),
        "new": sum(
            state.active_snapshot is None and failed_job(state) is None
            for state in states
        ),
    }
    return [
        AttentionRule(
            code=code, panel="scan", label=_ATTENTION_LABELS[code], count=count
        )
        for code, count in counts.items()
        if count
    ]


@router.get("/scan/excluded", response_model=list[ExcludedServiceResponse])
def list_excluded(db: Session = Depends(get_db)) -> list[ExcludedServiceResponse]:
    """Services deliberately kept out of scanning."""
    rows = db.scalars(
        select(ExcludedService).options(joinedload(ExcludedService.service))
    ).all()
    return [
        ExcludedServiceResponse(
            name=row.service.repo,
            reason=row.reason,
            excluded_by=row.excluded_by,
            excluded_at=row.excluded_at,
        )
        for row in rows
    ]


@router.get("/scan/services", response_model=ServicesResponse)
def list_services(
    db: Session = Depends(get_db),
    status: str = Query(default="all"),
    q: str = Query(default=""),
    sort: str = Query(default="quality"),
    rule: str | None = Query(default=None),
) -> ServicesResponse:
    """The registry table: filtered rows plus the count behind every chip.

    ``counts`` is computed with the search applied but the status filter
    ignored, so the chips keep showing where the rest of the matches went.
    """
    matched = [
        (service, state)
        for service, state in _all_services(db)
        if q.lower() in service.repo.lower()
    ]
    counts = {
        name: sum(_matches_filter(state, name) for _service, state in matched)
        for name in SERVICE_FILTERS
    }

    if rule is not None:
        selected = [pair for pair in matched if _matches_rule(pair[1], rule)]
    else:
        selected = [pair for pair in matched if _matches_filter(pair[1], status)]

    items = [
        ServiceListItem.from_service(service, state) for service, state in selected
    ]
    return ServicesResponse(items=_sorted(items, sort), counts=counts)


@router.get("/scan/services/{repo:path}/snapshots", response_model=SnapshotsResponse)
def list_snapshots(repo: str, db: Session = Depends(get_db)) -> SnapshotsResponse:
    """A service's scan history, newest first."""
    service = _service_or_404(db, repo)
    snapshots = db.scalars(
        select(Snapshot)
        .where(Snapshot.service_id == service.id)
        .order_by(Snapshot.created_at.desc(), Snapshot.id.desc())
    ).all()
    return SnapshotsResponse(
        items=[SnapshotResponse.from_snapshot(row) for row in snapshots],
        active_id=service.active_snapshot_id,
        latest_id=service.latest_snapshot_id,
    )


@router.get("/scan/services/{repo:path}/documents/{document_id}")
def get_document(
    repo: str, document_id: int, db: Session = Depends(get_db)
) -> DocumentDetailResponse:
    """One document of the active snapshot, with its sections and parameters."""
    service = _service_or_404(db, repo)
    record = db.scalar(
        select(DocumentRecord)
        .options(undefer(DocumentRecord.payload))
        .where(
            DocumentRecord.id == document_id,
            DocumentRecord.snapshot_id == service.active_snapshot_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetailResponse.from_record(
        record,
        repo=service.repo,
        commit_hash=service.active_snapshot.commit_hash,
    )


@router.get("/scan/services/{repo:path}/documents", response_model=DocumentsResponse)
def list_documents(
    repo: str,
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    section: str | None = Query(default=None),
    section_status: str | None = Query(default=None),
    issue: str | None = Query(default=None),
    api_version: str | None = Query(default=None),
) -> DocumentsResponse:
    """One page of the active snapshot's API documents.

    Pages that carry no scan status are not API documents; they are counted in
    the service detail's ``non_endpoint_documents`` instead of being listed here
    under a status they never had.

    ``section`` and ``section_status`` together answer "which documents have a
    failed body": both are required for the filter to apply, because either one
    alone would silently mean something else. ``issue`` answers the same
    question for a diagnostic code, and ``api_version`` narrows to one version
    of the API (``unversioned`` for the documents that name none).
    """
    service = _service_or_404(db, repo)
    if service.active_snapshot_id is None:
        return DocumentsResponse(
            items=[],
            total=0,
            page=page,
            page_size=PAGE_SIZE,
            doc_counts={"all": 0},
            version_counts={},
        )

    base = select(DocumentRecord).where(
        DocumentRecord.snapshot_id == service.active_snapshot_id,
        DocumentRecord.overall_status.is_not(None),
    )
    if q:
        pattern = f"%{q}%"
        base = base.where(
            or_(
                DocumentRecord.path.ilike(pattern),
                DocumentRecord.title.ilike(pattern),
                DocumentRecord.uri.ilike(pattern),
            )
        )
    if section and section_status:
        base = base.where(
            func.jsonb_path_exists(
                DocumentRecord.payload,
                sa_text("CAST(:section_match AS jsonpath)").bindparams(
                    section_match=_SECTION_MATCH
                ),
                func.jsonb_build_object("name", section, "status", section_status),
            )
        )
    if issue:
        base = base.where(
            func.jsonb_path_exists(
                DocumentRecord.payload,
                sa_text("CAST(:issue_match AS jsonpath)").bindparams(
                    issue_match=_ISSUE_MATCH
                ),
                func.jsonb_build_object("code", issue),
            )
        )

    # Both chip rows describe the same set: the counts are taken before the
    # chips' own filters are applied, so clicking one never makes the others
    # vanish - and the row a user just clicked stays there to be unclicked.
    doc_counts = _document_counts(db, base)
    version_counts = _version_counts(db, base)

    filtered = base.where(DocumentRecord.overall_status == status) if status else base
    if api_version:
        filtered = filtered.where(
            DocumentRecord.api_version.is_(None)
            if api_version == UNVERSIONED
            else DocumentRecord.api_version == api_version
        )

    total = db.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    records = db.scalars(
        filtered.options(undefer(DocumentRecord.payload))
        .order_by(_STATUS_ORDER, DocumentRecord.path)
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()

    return DocumentsResponse(
        items=[DocumentListItem.from_record(record) for record in records],
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        doc_counts=doc_counts,
        version_counts=version_counts,
    )


@router.get("/scan/services/{repo:path}/export")
def export_snapshot(repo: str, db: Session = Depends(get_db)) -> Response:
    """The active snapshot as a ``RepositoryScanResult`` - the scanner's own
    contract, not a shape invented for this endpoint.

    Rebuilt from the stored payloads and validated on the way out: if anything
    in the database no longer satisfies the contract, this fails loudly instead
    of handing out a file that only looks right.
    """
    service = _service_or_404(db, repo)
    snapshot = service.active_snapshot
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Service has no scan result")

    payloads = db.scalars(
        select(DocumentRecord)
        .options(undefer(DocumentRecord.payload))
        .where(DocumentRecord.snapshot_id == snapshot.id)
        .order_by(DocumentRecord.path)
    ).all()

    result = RepositoryScanResult(
        repository=IrService(
            repo=service.repo,
            documents=[document_from_payload(record.payload) for record in payloads],
        ),
        branch=snapshot.branch,
        commit_hash=snapshot.commit_hash,
        scanner_version=snapshot.scanner_version,
        excluded_documents=list(snapshot.excluded_documents),
    )
    filename = f"{service.name}-{snapshot.commit_hash[:7]}.json"
    return Response(
        content=json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/scan/services/{repo:path}", response_model=ServiceDetailResponse)
def get_service(repo: str, db: Session = Depends(get_db)) -> ServiceDetailResponse:
    """Everything the service page shows about one service."""
    service = _service_or_404(db, repo)
    state = derive_service_state(service, scanner_version=SCANNER_VERSION)
    return ServiceDetailResponse.from_service(service, state)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service_query():
    return select(Service).options(
        selectinload(Service.jobs),
        joinedload(Service.active_snapshot),
        joinedload(Service.latest_snapshot),
    )


def _service_or_404(db: Session, repo: str) -> Service:
    service = db.scalar(_service_query().where(Service.repo == repo))
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


def _all_services(db: Session) -> list[tuple[Service, ServiceState]]:
    services = db.scalars(_service_query().order_by(Service.repo)).unique().all()
    return [
        (service, derive_service_state(service, scanner_version=SCANNER_VERSION))
        for service in services
    ]


def _all_states(db: Session) -> list[ServiceState]:
    return [state for _service, state in _all_services(db)]


def _matches_filter(state: ServiceState, name: str) -> bool:
    if name == "all":
        return True
    if name == "needs_rescan":
        return state.rescan_reason is not None
    return state.scan_status.value == name


def _matches_rule(state: ServiceState, rule: str) -> bool:
    if rule == "failed":
        return failed_job(state) is not None
    if rule == "version":
        snapshot = state.active_snapshot
        return snapshot is not None and snapshot.scanner_version != SCANNER_VERSION
    if rule == "drift":
        return state.docs_changed
    if rule == "new":
        return state.active_snapshot is None and failed_job(state) is None
    return False


def _sorted(items: list[ServiceListItem], sort: str) -> list[ServiceListItem]:
    if sort == "name":
        return sorted(items, key=lambda item: item.name)
    if sort == "docs":
        return sorted(items, key=lambda item: (-(item.documents or 0), item.name))
    # quality: the documentation that needs the most work first, never-scanned last
    return sorted(
        items,
        key=lambda item: (item.docs_ok is None, item.docs_ok or 0, item.name),
    )


def _version_counts(db: Session, base: Select) -> dict[str, int]:
    """How the matching documents spread over API versions, worst-first order
    being irrelevant here: the UI sorts them itself.

    Documents that name no version are grouped under ``unversioned`` - the same
    key the snapshot analytics uses, so the two never disagree.
    """
    matched = base.subquery()
    rows = db.execute(
        select(matched.c.api_version, func.count()).group_by(matched.c.api_version)
    ).all()
    return {(version or UNVERSIONED): count for version, count in rows}


def _document_counts(db: Session, base: Select) -> dict[str, int]:
    """Per-status counts with the search applied and the status filter ignored.

    ``all`` is the sum of the status buckets, so the chips always account for
    every listed document.
    """
    matched = base.subquery()
    rows = db.execute(
        select(matched.c.overall_status, func.count()).group_by(
            matched.c.overall_status
        )
    ).all()
    counts = {status: count for status, count in rows if status is not None}
    counts["all"] = sum(counts.values())
    return counts
