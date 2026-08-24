"""snapshot last_scanned_at

Revision ID: f1aec34a6321
Revises: 9430782bbec1
Create Date: 2026-08-14 17:52:04.118902

Separates "when this result first appeared" from "when a scan last reproduced
it". Since 9430782bbec1 a rescan whose result is unchanged stores no Snapshot,
so ``created_at`` alone answers only the first question - a repository read
minutes ago looks untouched since its documentation last moved.

Added nullable, backfilled, then made NOT NULL. Every existing row was created
by a scan that succeeded at ``created_at`` and has not been re-confirmed since,
so that is its true value rather than a placeholder, and the backfill is total:
no row can be left without one.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1aec34a6321'
down_revision: Union[str, Sequence[str], None] = '9430782bbec1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'snapshot',
        sa.Column('last_scanned_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE snapshot SET last_scanned_at = created_at")
    op.alter_column(
        'snapshot',
        'last_scanned_at',
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('snapshot', 'last_scanned_at')
