"""layout row per service

Revision ID: 61ce186dc793
Revises: 0a36dd9c3da6
Create Date: 2026-11-04 13:34:25.830650

Records that a service's layout exists, apart from whether it has a resource,
and makes ``resource`` reference that row instead of ``service`` directly.

The backfill gives every service that already has a resource a ``layout`` row
by ``system``, so the new foreign key holds for existing rows.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '61ce186dc793'
down_revision: Union[str, Sequence[str], None] = '0a36dd9c3da6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'layout',
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['service_id'],
            ['service.id'],
            name=op.f('fk_layout_service_id_service'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('service_id', name=op.f('pk_layout')),
    )
    op.execute(
        "INSERT INTO layout (service_id, created_by) "
        "SELECT DISTINCT service_id, 'system' FROM resource"
    )
    op.drop_constraint(
        op.f('fk_resource_service_id_service'), 'resource', type_='foreignkey'
    )
    op.create_foreign_key(
        op.f('fk_resource_service_id_layout'),
        'resource',
        'layout',
        ['service_id'],
        ['service_id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f('fk_resource_service_id_layout'), 'resource', type_='foreignkey'
    )
    op.create_foreign_key(
        op.f('fk_resource_service_id_service'),
        'resource',
        'service',
        ['service_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.drop_table('layout')
