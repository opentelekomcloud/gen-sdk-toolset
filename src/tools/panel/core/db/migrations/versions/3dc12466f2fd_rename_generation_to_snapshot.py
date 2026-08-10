"""rename generation to snapshot

Revision ID: 3dc12466f2fd
Revises: cf213c53cb57
Create Date: 2026-08-03 15:53:33.812735

A pure rename: every statement is an ALTER ... RENAME, so rows, foreign keys
and the active/latest pointers are carried over untouched. Autogenerate was
deliberately not used - it sees a dropped table and a new one, which would
discard every persisted scan result.

The lists below are the whole contract of this migration. They were built by
introspecting a migrated database for every object whose name contains
"generation" and matching it against the names SQLAlchemy's naming convention
now produces, so nothing is left holding the old vocabulary. Renaming a table
does not rename anything attached to it, and renaming a column does not rename
its index; both are why the index list is explicit. Renaming a PRIMARY KEY or
UNIQUE constraint does rename its backing index, so those appear only under
constraints.

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3dc12466f2fd'
down_revision: Union[str, Sequence[str], None] = 'cf213c53cb57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_TABLE = "generation"
_NEW_TABLE = "snapshot"

#: (table, old column, new column). The table is the one holding the column,
#: which is never the renamed table itself.
_COLUMNS: list[tuple[str, str, str]] = [
    ("document", "generation_id", "snapshot_id"),
    ("service", "active_generation_id", "active_snapshot_id"),
    ("service", "latest_generation_id", "latest_snapshot_id"),
]

#: (table, old constraint, new constraint). Table names here are the ones in
#: effect while the statement runs - "snapshot" for the renamed table, because
#: upgrade renames it first and downgrade renames it last.
_CONSTRAINTS: list[tuple[str, str, str]] = [
    ("document", "fk_document_generation_id_generation", "fk_document_snapshot_id_snapshot"),
    ("document", "uq_document_generation_path", "uq_document_snapshot_path"),
    ("service", "fk_service_active_generation", "fk_service_active_snapshot"),
    ("service", "fk_service_latest_generation", "fk_service_latest_snapshot"),
    ("snapshot", "pk_generation", "pk_snapshot"),
    ("snapshot", "uq_generation_source_job_id", "uq_snapshot_source_job_id"),
    ("snapshot", "fk_generation_service_id_service", "fk_snapshot_service_id_service"),
    ("snapshot", "fk_generation_source_job_id_job", "fk_snapshot_source_job_id_job"),
    ("snapshot", "ck_generation_document_counts_match", "ck_snapshot_document_counts_match"),
    ("snapshot", "ck_generation_documents_total_non_negative", "ck_snapshot_documents_total_non_negative"),
    ("snapshot", "ck_generation_endpoints_total_non_negative", "ck_snapshot_endpoints_total_non_negative"),
    ("snapshot", "ck_generation_issues_total_non_negative", "ck_snapshot_issues_total_non_negative"),
    ("snapshot", "ck_generation_non_endpoint_documents_non_negative", "ck_snapshot_non_endpoint_documents_non_negative"),
    ("snapshot", "ck_generation_status_counts_non_negative", "ck_snapshot_status_counts_non_negative"),
]

#: (old sequence, new sequence). Renaming a table leaves its identity sequence
#: behind under the old name, where nothing but `pg_sequences` would ever show
#: it. Column defaults reference the sequence by OID, so the rename is
#: transparent to inserts.
_SEQUENCES: list[tuple[str, str]] = [
    ("generation_id_seq", "snapshot_id_seq"),
]

#: (old index, new index) for indexes that no constraint owns.
_INDEXES: list[tuple[str, str]] = [
    ("ix_generation_commit_hash", "ix_snapshot_commit_hash"),
    ("ix_generation_created_at", "ix_snapshot_created_at"),
    ("ix_generation_service_created_at", "ix_snapshot_service_created_at"),
    ("ix_generation_service_id", "ix_snapshot_service_id"),
    ("ix_document_generation_id", "ix_document_snapshot_id"),
    ("ix_document_generation_kind", "ix_document_snapshot_kind"),
    ("ix_document_generation_status", "ix_document_snapshot_status"),
    ("ix_document_generation_method", "ix_document_snapshot_method"),
    ("ix_document_generation_api_version", "ix_document_snapshot_api_version"),
    ("ix_service_active_generation_id", "ix_service_active_snapshot_id"),
    ("ix_service_latest_generation_id", "ix_service_latest_snapshot_id"),
]


def _rename_constraint(table: str, old: str, new: str) -> None:
    op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"')


def _rename_index(old: str, new: str) -> None:
    op.execute(f'ALTER INDEX "{old}" RENAME TO "{new}"')


def _rename_sequence(old: str, new: str) -> None:
    op.execute(f'ALTER SEQUENCE "{old}" RENAME TO "{new}"')


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table(_OLD_TABLE, _NEW_TABLE)

    for table, old_column, new_column in _COLUMNS:
        op.alter_column(table, old_column, new_column_name=new_column)

    for table, old_name, new_name in _CONSTRAINTS:
        _rename_constraint(table, old_name, new_name)

    for old_name, new_name in _INDEXES:
        _rename_index(old_name, new_name)

    for old_name, new_name in _SEQUENCES:
        _rename_sequence(old_name, new_name)


def downgrade() -> None:
    """Downgrade schema."""
    for old_name, new_name in _SEQUENCES:
        _rename_sequence(new_name, old_name)

    for old_name, new_name in _INDEXES:
        _rename_index(new_name, old_name)

    for table, old_name, new_name in _CONSTRAINTS:
        _rename_constraint(table, new_name, old_name)

    for table, old_column, new_column in _COLUMNS:
        op.alter_column(table, new_column, new_column_name=old_column)

    op.rename_table(_NEW_TABLE, _OLD_TABLE)
