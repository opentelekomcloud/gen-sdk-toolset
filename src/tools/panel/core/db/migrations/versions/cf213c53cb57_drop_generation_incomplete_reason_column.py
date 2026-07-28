"""drop generation incomplete_reason column

Revision ID: cf213c53cb57
Revises: e9bf9a6968a1
Create Date: 2026-07-28 15:31:12.981692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf213c53cb57'
down_revision: Union[str, Sequence[str], None] = 'e9bf9a6968a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('generation', 'incomplete_reason')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('generation', sa.Column('incomplete_reason', sa.Text(), nullable=True))
