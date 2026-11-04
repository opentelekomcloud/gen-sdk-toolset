"""layout resource tables

Revision ID: 0a36dd9c3da6
Revises: f1aec34a6321
Create Date: 2026-11-03 11:38:58.534547

Adds the layout tables, ``resource`` and ``resource_endpoint``, beside the Scan
tables, which this revision does not touch (ADR-0074). Autogenerate does not
see CHECK constraints reliably, so the two on ``resource`` are written by hand.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a36dd9c3da6'
down_revision: Union[str, Sequence[str], None] = 'f1aec34a6321'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'resource',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('api_version', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('confirmed_by', sa.String(length=255), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "name ~ '^[a-z][a-z0-9_]*$'",
            name=op.f('ck_resource_name_is_package_name'),
        ),
        sa.CheckConstraint(
            '(confirmed_by IS NULL) = (confirmed_at IS NULL)',
            name=op.f('ck_resource_confirmed_by_and_at_together'),
        ),
        sa.ForeignKeyConstraint(
            ['service_id'],
            ['service.id'],
            name=op.f('fk_resource_service_id_service'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_resource')),
        sa.UniqueConstraint('id', 'service_id', name='uq_resource_id_service'),
        sa.UniqueConstraint(
            'service_id',
            'api_version',
            'name',
            name='uq_resource_service_version_name',
        ),
    )
    op.create_table(
        'resource_endpoint',
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['resource_id', 'service_id'],
            ['resource.id', 'resource.service_id'],
            name='fk_resource_endpoint_resource',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint(
            'service_id', 'path', name=op.f('pk_resource_endpoint')
        ),
    )
    op.create_index(
        op.f('ix_resource_endpoint_resource_id'),
        'resource_endpoint',
        ['resource_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_resource_endpoint_resource_id'), table_name='resource_endpoint'
    )
    op.drop_table('resource_endpoint')
    op.drop_table('resource')
