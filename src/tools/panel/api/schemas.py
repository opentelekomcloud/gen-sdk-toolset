"""Pydantic request/response models for the scan launch and job API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from tools.panel.core.db.models import JobKind, JobStatus, RepositoryScanJob


class RescanRequest(BaseModel):
    """Body for launching a scan: who initiated it."""

    initiated_by: str


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
    def from_job(cls, job: RepositoryScanJob) -> "JobResponse":
        """Build the response from a Job, reading provenance from its Generation.

        ``scanner_version`` and ``commit_hash`` become available once ingest
        creates the Generation for a completed scan; until then they are None.
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
