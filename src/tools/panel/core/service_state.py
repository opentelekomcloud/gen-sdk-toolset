"""What a Service looks like right now, derived from its Jobs and Generations.

The panel's read endpoints all answer the same underlying question - is this
service scanned, scanning, stale or broken - so the rules live here once, in
domain terms, instead of being re-derived per endpoint in the HTTP layer.

Nothing here queries the database: it reads the ORM relationships the caller
already loaded, and it never writes.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from tools.panel.core.db.models import (
    Generation,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
)

_ACTIVE_STATUSES = (JobStatus.queued, JobStatus.running)


class ScanStatus(str, enum.Enum):
    """How the registry describes a service's scan state."""

    scanned = "scanned"
    partial = "partial"
    failed = "failed"
    not_scanned = "not_scanned"
    scanning = "scanning"


class RescanReason(str, enum.Enum):
    """Why the panel suggests rescanning, in priority order."""

    retry = "retry"
    partial = "partial"
    version = "version"
    drift = "drift"


@dataclass(frozen=True)
class ServiceState:
    """The derived view of one Service, shared by every read endpoint."""

    scan_status: ScanStatus
    rescan_reason: RescanReason | None
    docs_changed: bool
    active_generation: Generation | None
    latest_generation: Generation | None
    #: The queued or running scan job, when one exists.
    active_job: RepositoryScanJob | None
    #: The most recent job, whatever its state - the source of `error`.
    last_job: RepositoryScanJob | None


def derive_service_state(service: Service, *, scanner_version: str) -> ServiceState:
    """Return the current state of ``service``.

    :param service: A Service with its jobs and generation pointers loaded.
    :param scanner_version: The scanner version running now, to spot
        generations produced by an older one.
    """
    last_job = _last_job(service)
    active_job = _active_scan_job(service)
    generation = service.active_generation

    docs_changed = (
        service.head_commit is not None
        and generation is not None
        and service.head_commit != generation.commit_hash
    )
    scan_status = _scan_status(generation, active_job=active_job, last_job=last_job)

    return ServiceState(
        scan_status=scan_status,
        rescan_reason=_rescan_reason(
            generation,
            last_job=last_job,
            scan_status=scan_status,
            docs_changed=docs_changed,
            scanner_version=scanner_version,
        ),
        docs_changed=docs_changed,
        active_generation=generation,
        latest_generation=service.latest_generation,
        active_job=active_job,
        last_job=last_job,
    )


def status_documents(generation: Generation) -> int:
    """Documents that carry a scan status - the sum of the overall breakdown.

    Deliberately not ``documents_total``: pages that are not API documents have
    no status and are reported on their own, never folded into one they never
    had.

    :param generation: The generation to count.
    """
    return (
        generation.ok_count
        + generation.partial_count
        + generation.failed_count
        + generation.unsupported_count
    )


def failed_job(state: ServiceState) -> RepositoryScanJob | None:
    """The last job, but only while it is the failure the UI should surface.

    A failed job is a warning, not a data-loss state: the service keeps serving
    its active generation. The next successful scan replaces the last job and
    the warning disappears with it.
    """
    job = state.last_job
    if job is None or job.status is not JobStatus.failed:
        return None
    return job


def _last_job(service: Service) -> RepositoryScanJob | None:
    if not service.jobs:
        return None
    return max(service.jobs, key=lambda job: (job.created_at, job.id))


def _active_scan_job(service: Service) -> RepositoryScanJob | None:
    active = [
        job
        for job in service.jobs
        if job.kind is JobKind.scan and job.status in _ACTIVE_STATUSES
    ]
    if not active:
        return None
    # uq_active_scan_job_per_service allows at most one; take the newest anyway.
    return max(active, key=lambda job: (job.created_at, job.id))


def _scan_status(
    generation: Generation | None,
    *,
    active_job: RepositoryScanJob | None,
    last_job: RepositoryScanJob | None,
) -> ScanStatus:
    if active_job is not None:
        return ScanStatus.scanning
    if generation is None:
        if last_job is not None and last_job.status is JobStatus.failed:
            return ScanStatus.failed
        return ScanStatus.not_scanned
    if generation.partial_count or generation.failed_count:
        return ScanStatus.partial
    return ScanStatus.scanned


def _rescan_reason(
    generation: Generation | None,
    *,
    last_job: RepositoryScanJob | None,
    scan_status: ScanStatus,
    docs_changed: bool,
    scanner_version: str,
) -> RescanReason | None:
    """Priority order: retry, then partial, then version, then drift."""
    if scan_status is ScanStatus.scanning:
        return None
    if last_job is not None and last_job.status is JobStatus.failed:
        return RescanReason.retry
    if generation is None:
        return None
    if generation.partial_count or generation.failed_count:
        return RescanReason.partial
    if generation.scanner_version != scanner_version:
        return RescanReason.version
    if docs_changed:
        return RescanReason.drift
    return None
