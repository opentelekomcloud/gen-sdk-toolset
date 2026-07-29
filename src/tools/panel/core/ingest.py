"""Ingest a completed repository scan result into a persisted Generation.

Issue #16 (F14). This is the stable call site the scan runner hands its
completed result to: it takes a Job that is already ``running`` and a scan
result that already succeeded, and turns them into one immutable Generation
plus its documents, completing the Job in the same transaction.

Two contracts hold this module together:

* **Nothing is ingested quietly.** Every precondition that does not hold raises
  :class:`IngestRejected`; the runner turns that into a ``failed`` Job with the
  message recorded. A quiet return would leave the Job ``running`` forever -
  invisible in the UI and blocking the next scan through
  ``uq_active_scan_job_per_service``.
* **Everything becomes visible at once.** One ``commit()`` at the end is the
  only visibility boundary, so no reader can observe half the documents or a
  switched active-generation pointer before the Job says ``done``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from tools.panel.core.analytics import analyze_document, analyze_generation
from tools.panel.core.db.engine import SessionLocal, get_engine
from tools.panel.core.db.models import (
    DocumentRecord,
    Generation,
    JobKind,
    JobStatus,
    RepositoryScanJob,
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
    """Persist a completed scan result as a Generation and complete the Job.

    Opens its own session (background work never borrows the request's) and
    writes the Generation, its documents, the Service scan metadata and the
    Job's ``done`` transition in a single transaction.

    :param job_id: The ``running`` scan Job that produced this result.
    :param service_repo: The repository the Job asked to scan.
    :param result: A successful repository scan result.
    :raises IngestRejected: The Job is not a running scan job, the result is
        not a successful Service scan, or the repositories do not match.
    """
    get_engine()  # ensure SessionLocal is bound
    with SessionLocal() as session:
        job = session.get(RepositoryScanJob, job_id)
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
    """Write the Generation, its documents, the Service metadata and the Job."""
    # One timestamp for one event: the frontend reads generation.created_at as
    # the scan time, and job.finished_at is that same moment.
    finished_at = datetime.now(tz=UTC)
    analytics = analyze_generation(scanned.documents)

    generation = Generation(
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
    )
    session.add(generation)
    session.flush()  # assigns generation.id without ending the transaction
    session.add_all(_document_records(generation.id, scanned.documents))

    service = job.service
    service.has_api_ref = True  # the scan just read its api-ref path
    service.eligibility_checked_at = finished_at
    service.latest_generation_id = generation.id
    service.active_generation_id = generation.id
    # TODO(#25): head_commit is refreshed by drift detection, not by ingest -
    # the scanned commit is not necessarily the current branch HEAD.

    job.status = JobStatus.done
    job.finished_at = finished_at

    session.commit()
    logger.info(
        "job %s ingested as generation %s (%d documents, %d issues)",
        job.id,
        generation.id,
        analytics.documents_total,
        analytics.issues_total,
    )


def _document_records(
    generation_id: int, documents: Sequence[Document]
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
                generation_id=generation_id,
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
