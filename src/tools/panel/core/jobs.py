"""Background execution of a repository scan job: run the queued Job to a
terminal state and hand a successful result to ingest.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from tools.config import load_settings
from tools.panel.core.db.engine import SessionLocal, get_engine
from tools.panel.core.db.models import (
    TERMINAL_JOB_STATUSES,
    JobStatus,
    RepositoryScanJob,
)
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
    ``done`` transition and snapshot persistence belong to ingest
    (issue #16, F14).
    """
    settings = load_settings()
    get_engine()  # ensure SessionLocal is bound

    try:
        with SessionLocal() as session:
            job = session.get(RepositoryScanJob, job_id)
            if job is None:
                logger.warning("run_scan_job: job %s no longer exists", job_id)
                return
            repo = job.service.repo
            branch = job.service.branch
            # Conditional UPDATE, not check-then-write: a cancellation can land
            # between the two, and the plain write would resurrect a Job that
            # someone already finished.
            started = session.execute(
                update(RepositoryScanJob)
                .where(
                    RepositoryScanJob.id == job_id,
                    RepositoryScanJob.status == JobStatus.queued,
                )
                .values(status=JobStatus.running, started_at=datetime.now(tz=UTC))
            ).rowcount
            if not started:
                # Scheduled twice, already finalized, or cancelled before the
                # runner picked it up: never scan the same job again.
                session.rollback()
                logger.warning(
                    "run_scan_job: job %s is not queued any more — skipping", job_id
                )
                return
            session.commit()
    except Exception as exc:  # a Job stuck in queued blocks the service forever
        logger.exception("run_scan_job: could not mark job %s running", job_id)
        _fail_job(job_id, error=f"could not start job: {exc}")
        return
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

    if _is_terminal(job_id):
        # The Job was ended (normally a cancellation) while the scan was still
        # running. The scan could not be stopped, so it ran to completion - but
        # its result is discarded rather than persisted, and the Job keeps the
        # outcome it was already given. The discard is not silent: whatever
        # ended the Job wrote its reason into `job.error`.
        logger.warning(
            "run_scan_job: job %s was already finished when its scan returned — "
            "discarding the result instead of ingesting it",
            job_id,
        )
        return

    try:
        ingest_service_result(job_id=job_id, service_repo=repo, result=result)
    except Exception as exc:  # an ingest failure is also a job failure
        logger.exception("run_scan_job: ingest failed for job %s", job_id)
        _fail_job(job_id, error=f"ingest failed: {exc}")


def _is_terminal(job_id: int) -> bool:
    """True when nothing may move this Job any further - including when it is gone.

    A deleted Job counts as terminal for the caller's purposes: there is nothing
    left to ingest into.
    """
    get_engine()  # ensure SessionLocal is bound
    with SessionLocal() as session:
        status = session.scalar(
            select(RepositoryScanJob.status).where(RepositoryScanJob.id == job_id)
        )
    return status is None or status in TERMINAL_JOB_STATUSES


def terminate_job(job_id: int, reason: str) -> bool:
    """End a non-terminal Job now, recording ``reason`` as its error.

    Termination is a database decision only. ``BackgroundTasks`` runs the scan
    in a worker thread that cannot be cancelled from outside, so a scan already
    in flight keeps running; what this guarantees is that the Job is closed and
    that the scan's result is never persisted (see :func:`run_scan_job`, which
    re-checks the Job before handing anything to ingest).

    Returns ``True`` when this call ended the Job, ``False`` when it was already
    ``done`` or ``failed`` and was therefore left untouched. Callers that need to
    tell "cancelled" from "was already finished" - the API returning ``409`` -
    use that answer instead of reading the row again, which would be a race.

    :param job_id: The Job to end.
    :param reason: Recorded verbatim in ``error``; the Job's only account of
        why it stopped, so it should say who or what stopped it.
    """
    return _finalize_job(job_id, error=reason)


def terminate_orphaned_jobs() -> int:
    """End every Job left non-terminal by a previous process, and return the count.

    A ``queued`` or ``running`` Job does not survive a restart in any useful
    sense: the thread that was going to advance it is gone, so the row would sit
    there forever. It is not merely untidy - ``uq_active_scan_job_per_service``
    allows one active scan job per service, so each orphan permanently blocks
    its service from being scanned again.

    Called once from the API's lifespan hook. Safe to call when there is nothing
    to do; it commits only for the Jobs it actually ends.

    Unsafe with more than one API process: nothing here can tell an orphan from
    a Job a live sibling is still running, so a starting worker would terminate
    scans that are still in flight. Correct today because the image runs a
    single uvicorn worker (no ``--workers``); adding workers means giving Jobs
    an owner or a heartbeat first.
    """
    get_engine()  # ensure SessionLocal is bound
    with SessionLocal() as session:
        orphans = list(
            session.scalars(
                select(RepositoryScanJob.id).where(
                    RepositoryScanJob.status.not_in(TERMINAL_JOB_STATUSES)
                )
            )
        )

    terminated = sum(
        terminate_job(job_id, "interrupted by panel restart") for job_id in orphans
    )
    if terminated:
        logger.warning("terminated %d job(s) orphaned by a panel restart", terminated)
    else:
        logger.info("no jobs were left running by a previous panel process")
    return terminated


def _fail_job(
    job_id: int, *, error: str, interruption: dict[str, Any] | None = None
) -> None:
    """Fail a Job from the runner, carrying the structured interruption along."""
    _finalize_job(job_id, error=error, interruption=interruption)


def _finalize_job(
    job_id: int, *, error: str, interruption: dict[str, Any] | None = None
) -> bool:
    """Move a Job to ``failed`` unless it already reached a terminal state.

    One conditional UPDATE rather than read-then-write: the request thread and
    the background runner both end Jobs, and a SELECT followed by a commit would
    let them overwrite each other. Leaving terminal Jobs alone is what keeps a
    cancellation reason from being replaced by the provider error of the scan
    that was cancelled.
    """
    values: dict[str, Any] = {
        "status": JobStatus.failed,
        "error": error,
        "finished_at": datetime.now(tz=UTC),
    }
    if interruption is not None:
        values["interruption"] = interruption

    get_engine()  # ensure SessionLocal is bound
    with SessionLocal() as session:
        ended = session.execute(
            update(RepositoryScanJob)
            .where(
                RepositoryScanJob.id == job_id,
                RepositoryScanJob.status.not_in(TERMINAL_JOB_STATUSES),
            )
            .values(**values)
        ).rowcount
        if not ended:
            session.rollback()
            logger.info(
                "job %s is already finished — keeping its recorded outcome "
                "instead of overwriting it",
                job_id,
            )
            return False
        session.commit()
    return True


def _interruption_payload(result: RepositoryScanResult) -> dict[str, Any] | None:
    """Structured RepositoryInterruption for the ``job.interruption`` JSONB column.

    Serialized via ``dataclasses.asdict`` so a field added to
    ``RepositoryInterruption`` later cannot be dropped silently.
    """
    interruption = result.interruption
    if interruption is None:
        return None
    payload = dataclasses.asdict(interruption)
    payload["kind"] = interruption.kind.value  # enum -> plain string for JSONB
    return payload
