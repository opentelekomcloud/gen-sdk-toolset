"""PostgreSQL persistence models for the scanner panel."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tools.panel.core.db.base import Base


class JobKind(enum.StrEnum):
    scan = "scan"
    generate = "generate"
    maintain = "maintain"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


#: Statuses a Job can never move out of again. Cancellation and the background
#: runner write the same row from different threads, so both sides decide
#: "may I still change this Job?" against this one set rather than each
#: spelling out its own pair of statuses.
TERMINAL_JOB_STATUSES = frozenset({JobStatus.done, JobStatus.failed})


class Service(Base):
    """Repository registered in the panel.

    The Service owns the history of execution Jobs and successfully persisted
    Snapshots.

    active_snapshot_id selects the Snapshot displayed as the current
    repository scan result. It may point to any Snapshot belonging to this
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

    # Tri-state on purpose: NULL means "never checked", False means "checked
    # and has no API reference", True means eligible. A default would collapse
    # the first two into one value, and an unchecked repository would then be
    # indistinguishable from one discovery had ruled out - the read filters and
    # the scan guards below both turn on exactly that difference.
    has_api_ref: Mapped[bool | None] = mapped_column(
        sa.Boolean,
        nullable=True,
    )
    # Present when the service is excluded from scanning; None otherwise.
    # Rich exclusion data (who/when/why) lives in ExcludedService for the UI.
    exclusion: Mapped[ExcludedService | None] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
        uselist=False,
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
    head_checked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    active_snapshot_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey(
            "snapshot.id",
            name="fk_service_active_snapshot",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )

    # The most recently persisted Snapshot, regardless of which one is
    # displayed (active_snapshot_id may deliberately lag behind).
    latest_snapshot_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey(
            "snapshot.id",
            name="fk_service_latest_snapshot",
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

    snapshots: Mapped[list[Snapshot]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
        foreign_keys="Snapshot.service_id",
    )

    active_snapshot: Mapped[Snapshot | None] = relationship(
        foreign_keys=[active_snapshot_id],
        post_update=True,
    )

    latest_snapshot: Mapped[Snapshot | None] = relationship(
        foreign_keys=[latest_snapshot_id],
        post_update=True,
    )


class ExcludedService(Base):
    """Exclusion record for a service: who excluded it, when, and why.

    One row per excluded service; absence of a row means the service is
    eligible for scanning.
    """

    __tablename__ = "excluded_service"

    service_id: Mapped[int] = mapped_column(
        sa.ForeignKey(
            "service.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    reason: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )
    excluded_by: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    excluded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    service: Mapped[Service] = relationship(
        back_populates="exclusion",
    )


class RepositoryScanJob(Base):
    """One background operation attempt.

    Job owns execution lifecycle only. Successful scan data belongs to the
    Snapshot created from this Job.

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
            values_callable=lambda enum_class: [member.value for member in enum_class],
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
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
        default=JobStatus.queued,
        server_default=JobStatus.queued.value,
    )

    # Who triggered the job: a panel user login, or "system" for jobs
    # enqueued automatically (e.g. nightly discovery).
    initiated_by: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        default="system",
        server_default="system",
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

    # The Snapshot this Job's result is represented by: the one it created, or
    # the already-stored latest Snapshot when the result was identical to it.
    # Many Jobs may share one - unlike Snapshot.source_job_id, which names the
    # single Job that first produced it. NULL until a Job succeeds.
    result_snapshot_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey(
            "snapshot.id",
            name="fk_job_result_snapshot",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )

    service: Mapped[Service] = relationship(
        back_populates="jobs",
    )

    # The Snapshot this Job created, if it created one. A Job whose result
    # matched the latest Snapshot creates none but still has a result_snapshot.
    # Both sides name their foreign key explicitly: with two paths from job to
    # snapshot, SQLAlchemy cannot pick one for us.
    snapshot: Mapped[Snapshot | None] = relationship(
        back_populates="source_job",
        uselist=False,
        foreign_keys="Snapshot.source_job_id",
    )

    result_snapshot: Mapped[Snapshot | None] = relationship(
        foreign_keys=[result_snapshot_id],
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


class Snapshot(Base):
    """One successfully persisted repository scan result.

    A failed Job does not create a Snapshot, and neither does a successful one
    whose result is identical to the latest stored Snapshot - that Job points
    at the existing row through ``RepositoryScanJob.result_snapshot_id``. So a
    Snapshot marks a *change* in the scan result, not an execution attempt, and
    ``source_job_id`` names only the Job that first produced it.

    The *result* is immutable: nothing rewrites the commit, the analytics or
    the documents of a stored Snapshot. One field is not part of that result
    and does move - ``last_scanned_at``, which records the most recent scan
    that reproduced it. Without it an unchanged rescan would leave no trace at
    all, and the panel could not tell a repository read minutes ago from one
    nobody had looked at since its documentation last changed.

    Snapshot stores repository-level provenance, analytics, and the complete
    list of persisted document payloads produced by one successful scan.

    Named Snapshot rather than Generation so it cannot be confused with SDK
    code generation, where "generation" means emitted code.
    """

    __tablename__ = "snapshot"

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

    #: When this result was first seen.
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
    )
    #: When a successful scan last reproduced this result. Equal to
    #: ``created_at`` for a Snapshot nothing has re-confirmed yet, and moved
    #: forward by every unchanged rescan - which is the only mark such a scan
    #: leaves, since it stores no Snapshot of its own. The pair reads as "this
    #: result held from `created_at` and was still true at `last_scanned_at`".
    last_scanned_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    service: Mapped[Service] = relationship(
        back_populates="snapshots",
        foreign_keys=[service_id],
    )

    source_job: Mapped[RepositoryScanJob] = relationship(
        back_populates="snapshot",
        foreign_keys=[source_job_id],
    )

    documents: Mapped[list[DocumentRecord]] = relationship(
        back_populates="snapshot",
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
            "ix_snapshot_service_created_at",
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

    snapshot_id: Mapped[int] = mapped_column(
        sa.ForeignKey(
            "snapshot.id",
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

    snapshot: Mapped[Snapshot] = relationship(
        back_populates="documents",
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "snapshot_id",
            "path",
            name="uq_document_snapshot_path",
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
            "overall_status IS NULL OR overall_status IN "
            "('ok', 'partial', 'failed', 'unsupported')",
            name="overall_status_valid",
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
            "ix_document_snapshot_kind",
            "snapshot_id",
            "kind",
        ),
        sa.Index(
            "ix_document_snapshot_status",
            "snapshot_id",
            "overall_status",
        ),
        sa.Index(
            "ix_document_snapshot_method",
            "snapshot_id",
            "method",
        ),
        sa.Index(
            "ix_document_snapshot_api_version",
            "snapshot_id",
            "api_version",
        ),
    )


class Layout(Base):
    """A service's layout exists: who started its preliminary grouping, and when.

    One row per service. A service has a layout from the moment the grouping
    ran, whether or not it produced a resource - every endpoint may have gone to
    "unassigned" or "no version". Resources reference this row, so none can
    exist without it.
    """

    __tablename__ = "layout"

    service_id: Mapped[int] = mapped_column(
        sa.ForeignKey(
            "service.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    created_by: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


#: A resource name is free in its version (ADR-0065). Held as an object so a
#: layout edit tells a taken name by the name the table gives this constraint,
#: never by spelling that name a second time.
RESOURCE_NAME_UNIQUE_IN_VERSION = sa.UniqueConstraint(
    "service_id",
    "api_version",
    "name",
    name="uq_resource_service_version_name",
)


class Resource(Base):
    """One resource of a service's layout: a named group of its endpoints.

    Hangs off the service's Layout, not a Snapshot, so it outlives a rescan or
    an activation (ADR-0074). It becomes the Python SDK package
    ``services/<service>/<api_version>/<name>``, hence the version on every row
    and the package-name check on ``name`` (ADR-0065). ``id`` does not change on
    rename.

    ``(id, service_id)`` is unique only so ``resource_endpoint`` can reference
    both: that keeps an endpoint's service and its resource's service the same.
    """

    __tablename__ = "resource"

    id: Mapped[int] = mapped_column(primary_key=True)

    service_id: Mapped[int] = mapped_column(
        sa.ForeignKey(
            "layout.service_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    api_version: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    endpoints: Mapped[list[ResourceEndpoint]] = relationship(
        back_populates="resource",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        RESOURCE_NAME_UNIQUE_IN_VERSION,
        sa.UniqueConstraint(
            "id",
            "service_id",
            name="uq_resource_id_service",
        ),
        sa.CheckConstraint(
            "name ~ '^[a-z][a-z0-9_]*$'",
            name="name_is_package_name",
        ),
        sa.CheckConstraint(
            "(confirmed_by IS NULL) = (confirmed_at IS NULL)",
            name="confirmed_by_and_at_together",
        ),
    )


class ResourceEndpoint(Base):
    """An endpoint placed in a resource of its service's layout.

    Named by its document ``path``, not ``document.id``: document rows are
    rewritten by every scan, the path is not. The primary key
    ``(service_id, path)`` keeps an endpoint in at most one resource (ADR-0074).
    Endpoints in no resource are not stored.
    """

    __tablename__ = "resource_endpoint"

    service_id: Mapped[int] = mapped_column(
        primary_key=True,
    )
    path: Mapped[str] = mapped_column(
        sa.Text,
        primary_key=True,
    )
    resource_id: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )

    resource: Mapped[Resource] = relationship(
        back_populates="endpoints",
    )

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["resource_id", "service_id"],
            ["resource.id", "resource.service_id"],
            name="fk_resource_endpoint_resource",
            ondelete="CASCADE",
        ),
    )


__all__ = [
    "RESOURCE_NAME_UNIQUE_IN_VERSION",
    "TERMINAL_JOB_STATUSES",
    "DocumentRecord",
    "ExcludedService",
    "JobKind",
    "JobStatus",
    "Layout",
    "RepositoryScanJob",
    "Resource",
    "ResourceEndpoint",
    "Service",
    "Snapshot",
]
