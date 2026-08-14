"""Scan launch and job status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tools.panel.api.deps import get_db
from tools.panel.api.schemas import (
    ExcludeRequest,
    JobResponse,
    ScanRequest,
    StartScanResponse,
)
from tools.panel.core.db.models import (
    ExcludedService,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
)
from tools.panel.core.jobs import run_scan_job, terminate_job

router = APIRouter()


@router.post(
    "/scan/services/{repo:path}/rescan",
    status_code=202,
    response_model=StartScanResponse,
)
def start_scan(
    repo: str,
    body: ScanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> StartScanResponse:
    """Queue a scan Job for an existing Service and schedule it in the background.

    The Job is created ``queued`` and committed before scheduling; the Job ID is
    returned immediately without waiting for the scan.

    An excluded Service is a ``409``. The Service row is locked for the whole
    check so this cannot interleave with ``exclude_service``: without the lock
    both could read "not excluded yet" and commit, leaving a scan running
    against a service the operator had just hidden.
    """
    service = _locked_service_or_404(db, repo)
    if _exclusion_of(db, service) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Service {repo} is excluded from scanning",
        )

    job = RepositoryScanJob(
        service_id=service.id,
        kind=JobKind.scan,
        status=JobStatus.queued,
        initiated_by=body.initiated_by,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        # uq_active_scan_job_per_service: one queued/running scan per service.
        db.rollback()
        active = db.scalar(
            select(RepositoryScanJob)
            .where(
                RepositoryScanJob.service_id == service.id,
                RepositoryScanJob.status.in_((JobStatus.queued, JobStatus.running)),
            )
            .order_by(RepositoryScanJob.id.desc())
        )
        detail = (
            f"Scan job #{active.id} is already {active.status.value} for this service"
            if active is not None
            else "A scan is already queued or running for this service"
        )
        raise HTTPException(status_code=409, detail=detail) from exc
    db.refresh(job)

    background_tasks.add_task(run_scan_job, job.id)
    return StartScanResponse(job_id=job.id)


@router.post("/scan/services/{repo:path}/exclude", status_code=204)
def exclude_service(
    repo: str,
    body: ExcludeRequest,
    db: Session = Depends(get_db),
) -> None:
    """Hide a Service from the registry without deleting anything it owns.

    Exclusion is non-destructive: no Job, Snapshot or document row is touched,
    so restoring the Service brings back the same history it had. Only the
    listing endpoints filter it out - the detail endpoints keep answering, so
    the UI can still read an excluded Service in order to restore it.

    A Job already queued or running when this lands is deliberately left alone
    and will ingest its result normally. Killing it would mean either
    discarding a scan that already cost its rate-limit budget, or writing a
    half-ingested Snapshot; the exclusion takes effect from the next launch
    instead, which ``start_scan`` refuses.

    The Service row is locked for the whole check-then-insert, which is what
    makes that refusal reliable - see ``start_scan``.
    """
    service = _locked_service_or_404(db, repo)
    if _exclusion_of(db, service) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Service {repo} is already excluded",
        )

    db.add(
        ExcludedService(
            service_id=service.id,
            reason=body.reason,
            excluded_by=body.initiated_by,
        )
    )
    db.commit()


@router.post("/scan/services/{repo:path}/include", status_code=204)
def include_service(repo: str, db: Session = Depends(get_db)) -> None:
    """Restore an excluded Service to the registry.

    The exclusion row is deleted rather than archived, so no audit trail
    survives a restore - the reason text lives only while the exclusion does.
    Restoring a Service that is not excluded is a ``409`` rather than a silent
    no-op: it tells the caller their request changed nothing.
    """
    service = _locked_service_or_404(db, repo)
    exclusion = _exclusion_of(db, service)
    if exclusion is None:
        raise HTTPException(
            status_code=409,
            detail=f"Service {repo} is not excluded",
        )

    db.delete(exclusion)
    db.commit()


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobResponse:
    """Return one Job's state for frontend polling."""
    job = db.get(RepositoryScanJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_job(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: int, db: Session = Depends(get_db)) -> JobResponse:
    """Cancel a queued or running Job, returning its terminal state.

    Cancellation is a database-only operation: ``BackgroundTasks`` runs the scan
    in a worker thread that cannot be terminated from outside, so a scan already
    in flight keeps running to completion. What this guarantees is that the Job
    is closed and its result never persisted - the runner re-checks the Job
    before ingesting, and ingest refuses a Job that is no longer running.

    There is no ``cancelled`` status: a cancelled Job is ``failed`` with the
    reason in ``error``, so every consumer that already handles failure handles
    this too, and no persisted status is added that nothing would ever produce.
    Cancelling a Job that already finished is a ``409`` rather than a silent
    no-op - it tells the caller their cancellation changed nothing.
    """
    job = db.get(RepositoryScanJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # terminate_job answers "did I end it?" from the UPDATE itself; re-reading
    # the row to decide would be a race against the runner finishing normally.
    if not terminate_job(job_id, "cancelled by user"):
        # Re-read before reporting: the Job may have reached its terminal state
        # between the load above and the attempt, and naming the stale status
        # would tell the caller something that was never true.
        db.refresh(job)
        raise HTTPException(
            status_code=409,
            detail=f"Job #{job_id} is already {job.status.value}",
        )

    db.refresh(job)  # terminate_job committed in its own session
    return JobResponse.from_job(job)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _locked_service_or_404(db: Session, repo: str) -> Service:
    """Load one Service and hold a row lock on it until the request commits.

    Exclusion state has no unique index to lean on the way active Jobs do -
    ``ExcludedService`` is keyed by ``service_id``, which stops a double insert
    but says nothing about a scan launching at the same moment. Serializing
    every writer on the Service row is what closes that gap, so the check each
    of them makes is still true when it commits.
    """
    service = db.scalar(select(Service).where(Service.repo == repo).with_for_update())
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


def _exclusion_of(db: Session, service: Service) -> ExcludedService | None:
    """Read the Service's exclusion row, if any.

    Queried directly rather than through ``service.exclusion`` so the read is
    a fresh statement under the lock taken above, rather than whatever the
    identity map happens to be holding.
    """
    return db.scalar(
        select(ExcludedService).where(ExcludedService.service_id == service.id)
    )
