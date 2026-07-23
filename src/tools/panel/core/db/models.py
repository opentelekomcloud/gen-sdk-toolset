"""PostgreSQL persistence models for the scanner panel."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tools.panel.core.db.base import Base


class JobKind(str, enum.Enum):
    scan = "scan"
    generate = "generate"
    maintain = "maintain"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Service(Base):
    """Repository registered in the panel.

    The Service owns the history of execution Jobs and successfully persisted
    Generations.

    active_generation_id selects the Generation displayed as the current
    repository scan result. It may point to any Generation belonging to this
    Service, not necessarily the latest one.
    """

    __tablename__ = "service"

    id: Mapped[int] = mapped_column(primary_key=True)

    repo: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    branch: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )

    has_api_ref: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )
    is_excluded: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )

    first_seen: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    eligibility_checked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    discovery_error: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    head_commit: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    active_generation_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey(
            "generation.id",
            name="fk_service_active_generation",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )

    # The most recently persisted Generation, regardless of which one is
    # displayed (active_generation_id may deliberately lag behind).
    latest_generation_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey(
            "generation.id",
            name="fk_service_latest_generation",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    jobs: Mapped[list[RepositoryScanJob]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
    )

    generations: Mapped[list[Generation]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
        foreign_keys="Generation.service_id",
    )

    active_generation: Mapped[Generation | None] = relationship(
        foreign_keys=[active_generation_id],
        post_update=True,
    )

    latest_generation: Mapped[Generation | None] = relationship(
        foreign_keys=[latest_generation_id],
        post_update=True,
    )

    __table_args__ = (
        sa.Index(
            "ix_service_eligibility",
            "has_api_ref",
            "is_excluded",
        ),
    )


class RepositoryScanJob(Base):
    """One background operation attempt.

    Job owns execution lifecycle only. Successful scan data belongs to the
    Generation created from this Job.

    A queued or running Job has no finished_at.
    A failed Job may have no started_at when it was interrupted before the
    background runner started.
    """

    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)

    service_id: Mapped[int] = mapped_column(
        sa.ForeignKey(
            "service.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    kind: Mapped[JobKind] = mapped_column(
        sa.Enum(
            JobKind,
            name="job_kind",
            native_enum=False,
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=JobKind.scan,
        server_default=JobKind.scan.value,
    )

    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(
            JobStatus,
            name="job_status",
            native_enum=False,
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=JobStatus.queued,
        server_default=JobStatus.queued.value,
        index=True,
    )

    error: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    # Canonical RepositoryInterruption (kind/repository/message/reset_time)
    # when the scan stopped operationally; kept structured, not flattened
    # into the error text.
    interruption: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    service: Mapped[Service] = relationship(
        back_populates="jobs",
    )

    generation: Mapped[Generation | None] = relationship(
        back_populates="source_job",
        uselist=False,
    )

    __table_args__ = (
        sa.CheckConstraint(
            """
            (
                status = 'queued'
                AND started_at IS NULL
                AND finished_at IS NULL
            )
            OR
            (
                status = 'running'
                AND started_at IS NOT NULL
                AND finished_at IS NULL
            )
            OR
            (
                status = 'done'
                AND started_at IS NOT NULL
                AND finished_at IS NOT NULL
            )
            OR
            (
                status = 'failed'
                AND finished_at IS NOT NULL
            )
            """,
            name="status_timestamps",
        ),
        sa.CheckConstraint(
            "status != 'failed' OR error IS NOT NULL",
            name="failed_job_has_error",
        ),
        sa.Index(
            "ix_job_service_created_at",
            "service_id",
            "created_at",
        ),
        sa.Index(
            "ix_job_service_status",
            "service_id",
            "status",
        ),
        sa.Index(
            "uq_active_scan_job_per_service",
            "service_id",
            unique=True,
            postgresql_where=sa.text(
                "kind = 'scan' AND status IN ('queued', 'running')"
            ),
        ),
    )


class Generation(Base):
    """Immutable successfully persisted repository scan snapshot.

    A failed Job does not create a Generation.

    Generation stores repository-level provenance, analytics, and the complete
    list of persisted document payloads produced by one successful scan.
    """

    __tablename__ = "generation"

    id: Mapped[int] = mapped_column(primary_key=True)

    service_id: Mapped[int] = mapped_column(
        sa.ForeignKey(
            "service.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_job_id: Mapped[int] = mapped_column(
        sa.ForeignKey(
            "job.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    branch: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    commit_hash: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        index=True,
    )
    scanner_version: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    document_schema_version: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )

    incomplete_reason: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    excluded_documents: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text),
        nullable=False,
        default=list,
        server_default=sa.text("'{}'::text[]"),
    )

    documents_total: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    endpoints_total: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    non_endpoint_documents: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    issues_total: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    ok_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    partial_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    failed_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    unsupported_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    completeness: Mapped[float | None] = mapped_column(
        sa.Float,
        nullable=True,
    )

    analytics: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
    )

    service: Mapped[Service] = relationship(
        back_populates="generations",
        foreign_keys=[service_id],
    )

    source_job: Mapped[RepositoryScanJob] = relationship(
        back_populates="generation",
    )

    documents: Mapped[list[DocumentRecord]] = relationship(
        back_populates="generation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        sa.CheckConstraint(
            "documents_total >= 0",
            name="documents_total_non_negative",
        ),
        sa.CheckConstraint(
            "endpoints_total >= 0",
            name="endpoints_total_non_negative",
        ),
        sa.CheckConstraint(
            "non_endpoint_documents >= 0",
            name="non_endpoint_documents_non_negative",
        ),
        sa.CheckConstraint(
            "issues_total >= 0",
            name="issues_total_non_negative",
        ),
        sa.CheckConstraint(
            """
            ok_count >= 0
            AND partial_count >= 0
            AND failed_count >= 0
            AND unsupported_count >= 0
            """,
            name="status_counts_non_negative",
        ),
        sa.CheckConstraint(
            """
            endpoints_total + non_endpoint_documents = documents_total
            """,
            name="document_counts_match",
        ),
        sa.Index(
            "ix_generation_service_created_at",
            "service_id",
            "created_at",
        ),
    )


class DocumentRecord(Base):
    """Persistence envelope for one canonical shared document.

    This is deliberately not a second domain-level Document model.

    payload is the source of truth and contains the complete serialized
    tools.shared.ir.Document or tools.shared.ir.Endpoint instance, including
    its nested scan results.

    path, title, method, uri, and api_version are PostgreSQL-generated
    projections derived directly from payload. They cannot diverge from the
    canonical shared model.

    overall_status, completeness, and issues_count are panel analytics
    projections calculated during ingest.
    """

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)

    generation_id: Mapped[int] = mapped_column(
        sa.ForeignKey(
            "generation.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        deferred=True,
    )

    kind: Mapped[str] = mapped_column(
        sa.Text,
        sa.Computed(
            "payload ->> 'kind'",
            persisted=True,
        ),
        nullable=False,
    )

    path: Mapped[str] = mapped_column(
        sa.Text,
        sa.Computed(
            "payload ->> 'path'",
            persisted=True,
        ),
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(
        sa.Text,
        sa.Computed(
            "payload ->> 'title'",
            persisted=True,
        ),
        nullable=True,
    )

    method: Mapped[str | None] = mapped_column(
        sa.Text,
        sa.Computed(
            "payload ->> 'method'",
            persisted=True,
        ),
        nullable=True,
    )

    uri: Mapped[str | None] = mapped_column(
        sa.Text,
        sa.Computed(
            "payload ->> 'uri'",
            persisted=True,
        ),
        nullable=True,
    )

    api_version: Mapped[str | None] = mapped_column(
        sa.Text,
        sa.Computed(
            "payload ->> 'api_version'",
            persisted=True,
        ),
        nullable=True,
    )

    overall_status: Mapped[str | None] = mapped_column(
        sa.String(32),
        nullable=True,
        index=True,
    )

    completeness: Mapped[float | None] = mapped_column(
        sa.Float,
        nullable=True,
    )

    issues_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    generation: Mapped[Generation] = relationship(
        back_populates="documents",
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "generation_id",
            "path",
            name="uq_document_generation_path",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="payload_is_object",
        ),
        sa.CheckConstraint(
            "kind IN ('document', 'endpoint')",
            name="kind_valid",
        ),
        sa.CheckConstraint(
            "kind = 'endpoint' OR (method IS NULL AND uri IS NULL)",
            name="non_endpoint_has_no_method_uri",
        ),
        sa.CheckConstraint(
            "issues_count >= 0",
            name="issues_count_non_negative",
        ),
        sa.Index(
            "ix_document_generation_kind",
            "generation_id",
            "kind",
        ),
        sa.Index(
            "ix_document_generation_status",
            "generation_id",
            "overall_status",
        ),
        sa.Index(
            "ix_document_generation_method",
            "generation_id",
            "method",
        ),
        sa.Index(
            "ix_document_generation_api_version",
            "generation_id",
            "api_version",
        ),
    )


__all__ = [
    "DocumentRecord",
    "Generation",
    "RepositoryScanJob",
    "JobKind",
    "JobStatus",
    "Service",
]