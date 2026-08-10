"""Scan launch and job status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tools.panel.api.deps import get_db
from tools.panel.api.schemas import JobResponse, ScanRequest, StartScanResponse
from tools.panel.core.db.models import JobKind, JobStatus, RepositoryScanJob, Service
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
    """
    service = db.scalar(select(Service).where(Service.repo == repo))
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")

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
