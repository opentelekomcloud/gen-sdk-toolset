"""service head_checked_at

Revision ID: 5b7e2d91c4a8
Revises: 61ce186dc793
Create Date: 2026-11-09 11:20:00.000000

When discovery last read the branch HEAD stored in ``head_commit``. Left NULL
for existing rows: the next discovery run fills it.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b7e2d91c4a8'
down_revision: Union[str, Sequence[str], None] = '61ce186dc793'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'service',
        sa.Column('head_checked_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('service', 'head_checked_at')
