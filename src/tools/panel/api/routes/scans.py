"""Scan launch and job status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tools.panel.api.deps import get_db
from tools.panel.api.schemas import JobResponse, RescanRequest, StartScanResponse
from tools.panel.core.db.models import JobKind, JobStatus, RepositoryScanJob, Service
from tools.panel.core.jobs import run_scan_job

router = APIRouter()


@router.post(
    "/scan/services/{repo}/rescan",
    status_code=202,
    response_model=StartScanResponse,
)
def start_scan(
    repo: str,
    body: RescanRequest,
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
        raise HTTPException(
            status_code=409,
            detail="A scan is already queued or running for this service",
        ) from exc
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
