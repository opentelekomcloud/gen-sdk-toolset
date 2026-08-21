"""Ingest a completed repository scan result into a persisted Snapshot.

Issue #16 (F14). This is the stable call site the scan runner hands its
completed result to: it takes a Job that is already ``running`` and a scan
result that already succeeded, and completes the Job in the same transaction.
A result that differs from the latest stored one becomes a new Snapshot with
its documents; one that does not is recorded against the Snapshot already
holding it, so the history stays a record of changes rather than of attempts.

Two contracts hold this module together:

* **Nothing is ingested quietly.** Every precondition that does not hold raises
  :class:`IngestRejected`; the runner turns that into a ``failed`` Job with the
  message recorded. A quiet return would leave the Job ``running`` forever -
  invisible in the UI and blocking the next scan through
  ``uq_active_scan_job_per_service``.
* **Everything becomes visible at once.** One ``commit()`` at the end is the
  only visibility boundary, so no reader can observe half the documents or a
  switched active-snapshot pointer before the Job says ``done``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tools.panel.core.analytics import analyze_document, analyze_snapshot
from tools.panel.core.analytics.snapshot import SnapshotAnalytics
from tools.panel.core.db.engine import SessionLocal, get_engine
from tools.panel.core.db.models import (
    DocumentRecord,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
    Snapshot,
)
from tools.shared.exceptions import GenSdkError
from tools.shared.ir import DOCUMENT_SCHEMA_VERSION, Document
from tools.shared.ir import Service as IrService
from tools.shared.scan import RepositoryScanResult

logger = logging.getLogger(__name__)


class IngestRejected(GenSdkError):
    """The Job or the scan result did not satisfy the successful-ingest contract."""


def ingest_service_result(
    *, job_id: int, service_repo: str, result: RepositoryScanResult
) -> None:
    """Persist a completed scan result as a Snapshot and complete the Job.

    Opens its own session (background work never borrows the request's) and
    writes the Snapshot, its documents, the Service scan metadata and the
    Job's ``done`` transition in a single transaction.

    :param job_id: The ``running`` scan Job that produced this result.
    :param service_repo: The repository the Job asked to scan.
    :param result: A successful repository scan result.
    :raises IngestRejected: The Job is not a running scan job, the result is
        not a successful Service scan, or the repositories do not match.
    """
    get_engine()  # ensure SessionLocal is bound
    with SessionLocal() as session:
        # Locked for the length of this transaction: cancellation is a plain
        # UPDATE from the request thread, and without the lock it could land
        # between the status check below and the commit - persisting a snapshot
        # for a Job somebody had already stopped. Every remaining statement is
        # local database work, so nothing holds this lock across the network.
        job = session.scalar(
            select(RepositoryScanJob)
            .where(RepositoryScanJob.id == job_id)
            .with_for_update()
        )
        _reject_unless_running_scan_job(job, job_id)
        scanned = _validated_service(result, service_repo=service_repo, job=job)
        _persist(session, job=job, result=result, scanned=scanned)


def _reject_unless_running_scan_job(job: RepositoryScanJob | None, job_id: int) -> None:
    """Reject anything but the Job this ingest was started for.

    Ingest never creates a Job: a missing one is a rejection, not a reason to
    insert a replacement.
    """
    if job is None:
        raise IngestRejected(f"job {job_id} does not exist")
    if job.kind is not JobKind.scan:
        raise IngestRejected(f"job {job_id} is kind '{job.kind.value}', expected scan")
    if job.status is not JobStatus.running:
        raise IngestRejected(f"job {job_id} is '{job.status.value}', expected running")


def _validated_service(
    result: RepositoryScanResult, *, service_repo: str, job: RepositoryScanJob
) -> IrService:
    """Return the scanned Service, or reject a result that must not be stored.

    The runner already screens failed scans, but the contract belongs to this
    function: the nightly scan loop (issue #64) will call it from a second
    place.
    """
    if result.failure_message is not None:
        raise IngestRejected(
            f"refusing to ingest a failed scan: {result.failure_message}"
        )
    if result.commit_hash is None:
        raise IngestRejected("scan result has no resolved commit hash")

    repository = result.repository
    if not isinstance(repository, IrService):
        raise IngestRejected(
            f"scan result for {repository.repo} is not a Service "
            "(the repository has no api-ref)"
        )
    if service_repo != job.service.repo or repository.repo != service_repo:
        raise IngestRejected(
            "repository mismatch: "
            f"job={job.service.repo} requested={service_repo} "
            f"scanned={repository.repo}"
        )
    return repository


def _persist(
    session: Session,
    *,
    job: RepositoryScanJob,
    result: RepositoryScanResult,
    scanned: IrService,
) -> None:
    """Complete the Job, storing a Snapshot only when the result changed.

    A Snapshot is meant to be a snapshot: a point where the scan result was
    different, not a receipt for every execution. Re-scanning an unchanged
    repository would otherwise copy every document row again and push the
    history forward by an entry that says nothing.

    The comparison runs inside the transaction that already holds the Job's
    ``FOR UPDATE`` lock, so no second ingest can insert a Snapshot between the
    decision and the commit.
    """
    # One timestamp for one event: whichever Snapshot ends up representing this
    # scan is stamped with it, and job.finished_at is that same moment.
    finished_at = datetime.now(tz=UTC)
    analytics = analyze_snapshot(scanned.documents)
    service = job.service

    unchanged = _unchanged_from_latest(service.latest_snapshot, result, analytics)
    if unchanged is not None:
        _complete_reusing(session, job=job, snapshot=unchanged, finished_at=finished_at)
        return

    snapshot = Snapshot(
        service_id=job.service_id,
        source_job_id=job.id,
        branch=result.branch,
        commit_hash=result.commit_hash,
        scanner_version=result.scanner_version,
        document_schema_version=DOCUMENT_SCHEMA_VERSION,
        excluded_documents=list(result.excluded_documents),
        documents_total=analytics.documents_total,
        endpoints_total=analytics.endpoints_total,
        non_endpoint_documents=analytics.non_endpoint_documents,
        issues_total=analytics.issues_total,
        ok_count=analytics.ok_count,
        partial_count=analytics.partial_count,
        failed_count=analytics.failed_count,
        unsupported_count=analytics.unsupported_count,
        completeness=analytics.completeness,
        analytics=analytics.model_dump(mode="json"),
        created_at=finished_at,
        last_scanned_at=finished_at,
    )
    session.add(snapshot)
    session.flush()  # assigns snapshot.id without ending the transaction
    session.add_all(_document_records(snapshot.id, scanned.documents))

    _record_eligibility(service, finished_at)
    service.latest_snapshot_id = snapshot.id
    service.active_snapshot_id = snapshot.id
    # TODO(#25): head_commit is refreshed by drift detection, not by ingest -
    # the scanned commit is not necessarily the current branch HEAD.

    job.status = JobStatus.done
    job.finished_at = finished_at
    job.result_snapshot_id = snapshot.id

    session.commit()
    logger.info(
        "job %s ingested as snapshot %s (%d documents, %d issues)",
        job.id,
        snapshot.id,
        analytics.documents_total,
        analytics.issues_total,
    )


def _unchanged_from_latest(
    latest: Snapshot | None,
    result: RepositoryScanResult,
    analytics: SnapshotAnalytics,
) -> Snapshot | None:
    """Return the latest Snapshot when this result is identical to it.

    Three fields decide it. ``commit_hash`` and ``scanner_version`` say the
    same code read the same source; ``analytics`` is the whole reading of that
    source, so anything the panel reports moving - a count, a completeness, a
    per-version breakdown - is a difference. The denormalized counter columns
    are projections of that same value and would only ever repeat the answer.

    Document payloads are deliberately not compared. At an identical commit
    and scanner version they cannot differ, and comparing them would mean
    loading every stored payload on every scan to learn nothing.

    Compared against ``latest_snapshot`` and never ``active_snapshot``: active
    is a display choice an operator may have pinned to an older entry, and
    comparing against it would store a duplicate of whatever is on screen.
    """
    if latest is None:
        return None
    if (
        latest.commit_hash == result.commit_hash
        and latest.scanner_version == result.scanner_version
        and latest.analytics == analytics.model_dump(mode="json")
    ):
        return latest
    return None


def _complete_reusing(
    session: Session,
    *,
    job: RepositoryScanJob,
    snapshot: Snapshot,
    finished_at: datetime,
) -> None:
    """Finish an unchanged scan against the Snapshot that already holds it.

    The Job is a full success - it reached the repository and read it - so it
    completes as ``done`` and refreshes the eligibility the scan just proved.
    What it does not do is move either pointer: there is no new Snapshot to
    move them to, and re-pointing ``active`` at ``latest`` would silently undo
    an operator's decision to pin an older entry.

    Moving ``last_scanned_at`` is the one mark this scan leaves. Without it a
    rescan that changed nothing would be indistinguishable from never having
    run, and the panel would report a repository read seconds ago as untouched
    since its documentation last moved.
    """
    snapshot.last_scanned_at = finished_at
    _record_eligibility(job.service, finished_at)
    job.status = JobStatus.done
    job.finished_at = finished_at
    job.result_snapshot_id = snapshot.id

    session.commit()
    logger.info("job %s produced no change; reusing snapshot %s", job.id, snapshot.id)


def _record_eligibility(service: Service, checked_at: datetime) -> None:
    """A completed scan is itself proof the api-ref path was there to read."""
    service.has_api_ref = True
    service.eligibility_checked_at = checked_at


def _document_records(
    snapshot_id: int, documents: Sequence[Document]
) -> list[DocumentRecord]:
    """Build one persistence envelope per scanned document.

    ``kind``, ``path``, ``title``, ``method``, ``uri`` and ``api_version`` are
    deliberately absent: PostgreSQL generates them from ``payload``, so they
    cannot drift away from the canonical shared model.
    """
    records = []
    for document in documents:
        stats = analyze_document(document)
        records.append(
            DocumentRecord(
                snapshot_id=snapshot_id,
                payload=document.model_dump(mode="json"),
                overall_status=(
                    stats.overall_status.value
                    if stats.overall_status is not None
                    else None
                ),
                completeness=stats.completeness,
                issues_count=stats.issues_count,
            )
        )
    return records
