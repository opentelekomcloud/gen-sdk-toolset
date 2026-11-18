"""snapshot exclusion reasons

Revision ID: 07707d4e971f
Revises: 5b7e2d91c4a8
Create Date: 2026-11-17 12:00:00.000000

``snapshot.excluded_documents`` changes from a list of paths to a list of
``ExcludedDocument`` payloads (path, reason, evidence), and
``snapshot.review_candidates`` is added for counted pages with an unclear
lifecycle notice.

A stored Snapshot is immutable, so existing paths are carried over as they are,
in order, with the reason ``unrecorded`` and no evidence. Inferring a reason
from the path would rewrite what an old scan decided. PostgreSQL does not allow
a subquery in ``ALTER COLUMN ... USING``, so the list is rebuilt into a new
column, which then takes the old one's place.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '07707d4e971f'
down_revision: Union[str, Sequence[str], None] = '5b7e2d91c4a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'snapshot',
        sa.Column(
            'excluded_documents_v2',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE snapshot SET excluded_documents_v2 = COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'path', entry.path,
                        'reason', 'unrecorded',
                        'evidence', NULL
                    )
                    ORDER BY entry.position
                )
                FROM unnest(snapshot.excluded_documents)
                    WITH ORDINALITY AS entry(path, position)
            ),
            '[]'::jsonb
        )
        """
    )
    op.drop_column('snapshot', 'excluded_documents')
    op.alter_column(
        'snapshot', 'excluded_documents_v2', new_column_name='excluded_documents'
    )
    op.add_column(
        'snapshot',
        sa.Column(
            'review_candidates',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema.

    Keeps the paths, in order; reasons, evidence and review candidates have no
    place in the old schema and are dropped.
    """
    op.drop_column('snapshot', 'review_candidates')
    op.add_column(
        'snapshot',
        sa.Column(
            'excluded_documents_v1',
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE snapshot SET excluded_documents_v1 = ARRAY(
            SELECT entry.value ->> 'path'
            FROM jsonb_array_elements(snapshot.excluded_documents)
                WITH ORDINALITY AS entry(value, position)
            ORDER BY entry.position
        )
        """
    )
    op.drop_column('snapshot', 'excluded_documents')
    op.alter_column(
        'snapshot', 'excluded_documents_v1', new_column_name='excluded_documents'
    )
