"""SQLAlchemy models persisting the canonical shared scan contract.

The schema mirrors ``tools.shared`` (PostgreSQL-first):

* ``Service`` rows keep repository identity in ``repo`` and carry the
  repository-level snapshot fields of ``RepositoryScanResult``.
* ``Document`` rows store one ``tools.shared.ir.Document``/``Endpoint`` per
  scan job. The ``kind`` column distinguishes the two explicitly; ``path``
  is the document identity within a job. The canonical endpoint sections
  (parameters, examples, section scan results) round-trip losslessly through
  the ``sections`` JSONB column; values used for listing/filtering are
  promoted to real columns.
* ``Issue`` rows denormalize scanner diagnostics for filtering/aggregation.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tools.panel.core.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobKind(enum.Enum):
    scan = "scan"
    generate = "generate"
    maintain = "maintain"


class JobStatus(enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Job(Base):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)

    kind: Mapped[JobKind] = mapped_column(sa.Enum(JobKind, native_enum=False))
    target: Mapped[str]
    status: Mapped[JobStatus] = mapped_column(sa.Enum(JobStatus, native_enum=False))

    scanner_version: Mapped[str | None]
    commit_hash: Mapped[str | None]

    docs_total: Mapped[int | None]
    ok_count: Mapped[int | None]
    partial_count: Mapped[int | None]
    failed_count: Mapped[int | None]
    unsupported_count: Mapped[int | None]
    issues_count: Mapped[int | None]

    error: Mapped[str | None]

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=_utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Service(Base):
    """One scanned repository (``RepositoryScanResult`` snapshot)."""

    __tablename__ = "service"

    id: Mapped[int] = mapped_column(primary_key=True)

    repo: Mapped[str] = mapped_column(unique=True)  # org/name — repository identity
    name: Mapped[str]
    branch: Mapped[str]
    has_api_ref: Mapped[bool]

    error: Mapped[str | None]
    incomplete_reason: Mapped[str | None]
    # RepositoryInterruption (kind/repository/message/reset_time), when the
    # scan was stopped operationally.
    interruption: Mapped[dict | None] = mapped_column(JSONB)
    excluded_documents: Mapped[list | None] = mapped_column(JSONB)

    scanned_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    scanner_version: Mapped[str | None]
    commit_hash: Mapped[str | None]

    head_commit: Mapped[str | None]
    non_endpoint_documents: Mapped[int | None]

    current_job_id: Mapped[int | None] = mapped_column(sa.ForeignKey("job.id"))
    previous_job_id: Mapped[int | None] = mapped_column(sa.ForeignKey("job.id"))


class DocKind(enum.Enum):
    """Mirrors the ``kind`` discriminator of ``tools.shared.ir`` documents."""

    document = "document"
    endpoint = "endpoint"


class DocStatus(enum.Enum):
    """Mirrors ``tools.domain.report.enums.OverallStatus``."""

    ok = "ok"
    partial = "partial"
    unsupported = "unsupported"
    failed = "failed"


class Document(Base):
    """One canonical ``Document``/``Endpoint`` observed by one scan job."""

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)

    service_id: Mapped[int] = mapped_column(sa.ForeignKey("service.id"), index=True)
    job_id: Mapped[int] = mapped_column(sa.ForeignKey("job.id"), index=True)

    kind: Mapped[DocKind] = mapped_column(sa.Enum(DocKind, native_enum=False))
    path: Mapped[str]  # repository-relative document path (canonical identity)
    title: Mapped[str | None]

    # Endpoint-only fields; enforced by ck_document_endpoint_fields below.
    method: Mapped[str | None]
    uri: Mapped[str | None]
    api_version: Mapped[str | None]

    # Canonical DocumentScanResult.failure_reason (Issue: code/location/details).
    failure_reason: Mapped[dict | None] = mapped_column(JSONB)

    overall_status: Mapped[DocStatus | None] = mapped_column(
        sa.Enum(DocStatus, native_enum=False)
    )
    # Null when completeness cannot be calculated (e.g. failed/unsupported
    # documents or plain documents without sections).
    completeness: Mapped[float | None]

    # Canonical Endpoint.sections, serialized losslessly (parameters with
    # nested children, examples, section scan results). Null for plain
    # documents, which have no sections in the shared contract.
    sections: Mapped[list | None] = mapped_column(JSONB, deferred=True)

    __table_args__ = (
        sa.UniqueConstraint("job_id", "path"),
        sa.CheckConstraint(
            "(kind = 'endpoint' AND method IS NOT NULL AND uri IS NOT NULL)"
            " OR (kind = 'document' AND method IS NULL AND uri IS NULL"
            "     AND sections IS NULL)",
            name="endpoint_fields",
        ),
    )


class Issue(Base):
    """Denormalized scanner diagnostic for filtering and aggregation."""

    __tablename__ = "issue"

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        sa.ForeignKey("document.id", ondelete="CASCADE")
    )
    service_id: Mapped[int] = mapped_column(sa.ForeignKey("service.id"))
    job_id: Mapped[int] = mapped_column(sa.ForeignKey("job.id"), index=True)

    code: Mapped[str] = mapped_column(index=True)
    location: Mapped[str | None]
    details: Mapped[str | None]
