"""job result_snapshot_id

Revision ID: 9430782bbec1
Revises: 3c0847043ef9
Create Date: 2026-08-14 16:20:36.955538

Gives every successful Job a pointer to the Snapshot its result is represented
by. Until now that link only existed in the other direction, as
``snapshot.source_job_id``, which can only ever name one Job - fine while every
successful scan created its own Snapshot, and wrong as soon as a scan whose
result is unchanged reuses the stored one.

The backfill is the part autogenerate cannot see. Existing rows have exactly
one Snapshot per successful Job, so the old direction is a complete and
authoritative source for the new column: every Job that created a Snapshot gets
it as its result. Jobs that failed, or never finished, keep NULL - they have no
result to point at, which is the same thing the column means going forward.

The foreign key is created with ``use_alter``: ``snapshot.source_job_id``
already points at ``job``, so the two tables now reference each other and
neither can be created first.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9430782bbec1'
down_revision: Union[str, Sequence[str], None] = '3c0847043ef9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('job', sa.Column('result_snapshot_id', sa.Integer(), nullable=True))
    op.create_index(
        op.f('ix_job_result_snapshot_id'), 'job', ['result_snapshot_id'], unique=False
    )
    op.create_foreign_key(
        'fk_job_result_snapshot',
        'job',
        'snapshot',
        ['result_snapshot_id'],
        ['id'],
        ondelete='SET NULL',
        use_alter=True,
    )
    op.execute(
        """
        UPDATE job SET result_snapshot_id = snapshot.id
        FROM snapshot WHERE snapshot.source_job_id = job.id
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_job_result_snapshot', 'job', type_='foreignkey')
    op.drop_index(op.f('ix_job_result_snapshot_id'), table_name='job')
    op.drop_column('job', 'result_snapshot_id')
