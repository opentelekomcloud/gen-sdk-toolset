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
    """How completely the panel managed to read a service.

    This is a statement about the scan, not about the documentation. A document
    full of malformed tables that we nevertheless read end to end leaves the
    service ``scanned``; its quality is reported separately as the clean-document
    share. ``partial`` means something stayed unread: a document we could not
    interpret at all, or parameter rows we could not recognize.
    """

    scanned = "scanned"
    partial = "partial"
    failed = "failed"
    not_scanned = "not_scanned"
    scanning = "scanning"


class RescanReason(str, enum.Enum):
    """Why the panel suggests rescanning, in priority order.

    Documents that came out partial are deliberately not a reason: the same
    commit scanned by the same scanner produces the same result, so offering a
    rescan would promise a change that cannot happen. Partial documents are a
    documentation problem, and the panel reports them as one.
    """

    retry = "retry"
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


def clean_endpoint_share(generation: Generation) -> float | None:
    """How much of this documentation a generator can use, 0..1.

    Documents are weighted rather than counted: clean 1, degraded 0.5, and 0
    for the ones we could not interpret at all - a document with one awkward
    table is not worth the same as one we cannot read, and neither is worth
    zero. Diagnostics about our own shortfall, and anything found in an example
    section, are excluded: neither says whether the endpoint can be generated.
    ``None`` when the generation has no document with a status: unknown, not
    zero.

    :param generation: The generation to measure.
    """
    total = status_documents(generation)
    if total == 0:
        return None
    usable = generation.analytics.get("usable_documents")
    if usable is None:
        # Ingested before documents were weighted; the clean count is the
        # closest honest answer that generation can give.
        usable = generation.analytics.get("documentation_clean", generation.ok_count)
    return usable / total


def read_in_full_share(generation: Generation) -> float | None:
    """Share of documents the scanner read end to end.

    The honest answer to "how well did we do": ``Generation.completeness`` only
    measures parameter rows, so it happily reports 100% for a document whose
    example section was never read. ``None`` when nothing carries a status.

    :param generation: The generation to measure.
    """
    total = status_documents(generation)
    if total == 0:
        return None
    read = generation.analytics.get("read_in_full")
    if read is None:
        return None  # ingested before this was counted: unknown, not 100%
    return read / total


def unread_documents(generation: Generation) -> int:
    """Documents where something stayed unread - our gap, not the docs'.

    :param generation: The generation to inspect.
    """
    return generation.analytics.get("unread_documents", 0)


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
    if generation.failed_count or generation.unsupported_count:
        return ScanStatus.partial  # documents we could not interpret at all
    if unread_documents(generation):
        return ScanStatus.partial  # content we saw and could not read
    if generation.completeness is not None and generation.completeness < 1:
        return ScanStatus.partial  # parameter rows we could not recognize
    return ScanStatus.scanned


def _rescan_reason(
    generation: Generation | None,
    *,
    last_job: RepositoryScanJob | None,
    scan_status: ScanStatus,
    docs_changed: bool,
    scanner_version: str,
) -> RescanReason | None:
    """Priority order: retry, then version, then drift."""
    if scan_status is ScanStatus.scanning:
        return None
    if last_job is not None and last_job.status is JobStatus.failed:
        return RescanReason.retry
    if generation is None:
        return None
    if generation.scanner_version != scanner_version:
        return RescanReason.version
    if docs_changed:
        return RescanReason.drift
    return None
