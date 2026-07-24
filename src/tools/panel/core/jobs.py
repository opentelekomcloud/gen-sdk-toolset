"""Background execution of repository scan jobs.

A scan is launched as a FastAPI BackgroundTask (see api/routes/scans.py); this
module runs the queued Job to a terminal state. The ``job`` table is a status
record for polling, not a queue.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from tools.config import load_settings
from tools.panel.core.db.engine import SessionLocal, get_engine
from tools.panel.core.db.models import JobStatus, RepositoryScanJob
from tools.panel.core.ingest import ingest_service_result
from tools.scanner.factory import build_scanner
from tools.shared.scan import RepositoryScanResult

logger = logging.getLogger(__name__)


def run_scan_job(job_id: int) -> None:
    """Run one queued scan Job to a terminal state.

    Opens its own session, transitions the Job ``queued -> running`` (committing
    ``started_at`` before any provider work), scans OUTSIDE an open transaction,
    then hands a successful result to ingest. A provider failure, an ingest
    failure, or any unexpected error transitions the Job to ``failed`` with the
    error recorded — the runner never leaves a Job stuck in ``running``. The
    ``done`` transition and generation persistence belong to ingest (next task).
    """
    settings = load_settings()
    get_engine()  # ensure SessionLocal is bound

    with SessionLocal() as session:
        job = session.get(RepositoryScanJob, job_id)
        if job is None:
            logger.warning("run_scan_job: job %s no longer exists", job_id)
            return
        repo = job.service.repo
        branch = job.service.branch
        job.status = JobStatus.running
        job.started_at = datetime.now(tz=timezone.utc)
        session.commit()
    # session closed -> no open transaction during provider work

    try:
        result = build_scanner(settings).scan_repository(repo=repo, branch=branch)
    except Exception as exc:  # unexpected provider/runtime failure
        logger.exception("run_scan_job: scan crashed for job %s", job_id)
        _fail_job(job_id, error=f"scan crashed: {exc}")
        return

    if result.failure_message is not None:
        # Provider interruption or scan error: no usable result to ingest.
        logger.warning(
            "run_scan_job: job %s scan failed: %s", job_id, result.failure_message
        )
        _fail_job(
            job_id,
            error=result.failure_message,
            interruption=_interruption_payload(result),
        )
        return

    try:
        ingest_service_result(job_id=job_id, service_repo=repo, result=result)
    except Exception as exc:  # ingest/database failure is a job failure (ADR-001)
        logger.exception("run_scan_job: ingest failed for job %s", job_id)
        _fail_job(job_id, error=f"ingest failed: {exc}")


def _fail_job(
    job_id: int, *, error: str, interruption: dict[str, Any] | None = None
) -> None:
    """Transition a Job to ``failed`` with the error (and interruption) recorded."""
    with SessionLocal() as session:
        job = session.get(RepositoryScanJob, job_id)
        if job is None:  # pragma: no cover - job deleted mid-flight
            return
        job.status = JobStatus.failed
        job.error = error
        job.finished_at = datetime.now(tz=timezone.utc)
        if interruption is not None:
            job.interruption = interruption
        session.commit()


def _interruption_payload(result: RepositoryScanResult) -> dict[str, Any] | None:
    """Structured RepositoryInterruption for the ``job.interruption`` JSONB column."""
    interruption = result.interruption
    if interruption is None:
        return None
    return {
        "kind": interruption.kind.value,
        "repository": interruption.repository,
        "message": interruption.message,
        "reset_time": interruption.reset_time,
    }
