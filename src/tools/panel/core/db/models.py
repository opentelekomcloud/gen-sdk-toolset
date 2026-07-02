from __future__ import annotations

import enum
from datetime import datetime, timezone

import sqlalchemy as sa
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

    kind: Mapped[JobKind] = mapped_column(
        sa.Enum(JobKind, native_enum=False)
    )
    target: Mapped[str]
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(JobStatus, native_enum=False)
    )

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
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )


class Service(Base):
    __tablename__ = "service"

    id: Mapped[int] = mapped_column(primary_key=True)

    repo: Mapped[str] = mapped_column(unique=True)  # org/name
    name: Mapped[str]
    branch: Mapped[str]
    has_api_ref: Mapped[bool]

    error: Mapped[str | None]
    scanned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    scanner_version: Mapped[str | None]
    commit_hash: Mapped[str | None]

    head_commit: Mapped[str | None]
    non_endpoint_documents: Mapped[int | None]

    current_job_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("job.id")
    )
    previous_job_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("job.id")
    )


class DocStatus(enum.Enum):
    ok = "ok"
    partial = "partial"
    unsupported = "unsupported"
    failed = "failed"


class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)

    service_id: Mapped[int] = mapped_column(sa.ForeignKey("service.id"),
                                            index=True)
    job_id: Mapped[int] = mapped_column(sa.ForeignKey("job.id"),
                                        index=True)

    document: Mapped[str]  # path to rst
    method: Mapped[str | None]
    uri: Mapped[str | None]
    title: Mapped[str | None]
    api_version: Mapped[str | None]
    failure_reason: Mapped[str | None]

    overall_status: Mapped[DocStatus] = mapped_column(
        sa.Enum(DocStatus, native_enum=False)
    )
    completeness: Mapped[float]

    sections: Mapped[dict] = mapped_column(sa.JSON, deferred=True)

    __table_args__ = (
        sa.UniqueConstraint("job_id", "document"),
    )


class Issue(Base):
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
