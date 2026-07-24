"""Background execution of repository scan jobs.

A scan is launched as a FastAPI BackgroundTask (see api/routes/scans.py); this
module runs the queued Job up to a completed RepositoryScanResult and hands it
to ingest. The ``job`` table is a status record for polling, not a queue.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from tools.config import load_settings
from tools.panel.core.db.engine import SessionLocal, get_engine
from tools.panel.core.db.models import JobStatus, RepositoryScanJob
from tools.panel.core.ingest import ingest_service_result
from tools.scanner.factory import build_scanner

logger = logging.getLogger(__name__)


def run_scan_job(job_id: int) -> None:
    """Run one queued scan Job up to a completed RepositoryScanResult.

    Opens its own session, transitions the Job ``queued -> running`` and commits
    that (with ``started_at``) before any provider work, then scans OUTSIDE an
    open transaction and hands the completed result to ingest. Persistence, the
    ``done``/``failed`` transition and ``finished_at`` belong to ingest (next
    task).
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

    result = build_scanner(settings).scan_repository(repo=repo, branch=branch)
    ingest_service_result(job_id=job_id, service_repo=repo, result=result)
