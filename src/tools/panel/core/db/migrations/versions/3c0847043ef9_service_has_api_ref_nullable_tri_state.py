"""service has_api_ref nullable tri-state

Revision ID: 3c0847043ef9
Revises: 3dc12466f2fd
Create Date: 2026-08-13 16:55:58.749583

`service.has_api_ref` becomes a tri-state: NULL is "never checked", false is
"checked, no API reference", true is eligible. Before this, both unchecked and
ineligible repositories read as false, so the read filters could not tell a
repository discovery had ruled out from one it had never looked at.

Autogenerate produced only the NOT NULL drop. Two things it cannot see had to
be added by hand, and both are load-bearing:

* the ``DEFAULT false`` is dropped. Left in place, every row inserted without an
  explicit value would land on "checked and ineligible" - a claim discovery
  never made - and the new value would be unreachable for new rows.
* the backfill. Existing rows carry false for both meanings, and only
  ``eligibility_checked_at`` distinguishes them: a row that was never checked
  has no timestamp, so its false is the placeholder rather than a result.

The downgrade re-collapses the two, which is lossy by nature - a NULL becomes
false, and the distinction this revision introduced is gone. It runs before the
NOT NULL is restored, since the constraint would otherwise reject those rows.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c0847043ef9'
down_revision: Union[str, Sequence[str], None] = '3dc12466f2fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'service',
        'has_api_ref',
        existing_type=sa.BOOLEAN(),
        nullable=True,
        server_default=None,
        existing_server_default=sa.text('false'),
    )
    op.execute(
        "UPDATE service SET has_api_ref = NULL WHERE eligibility_checked_at IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE service SET has_api_ref = false WHERE has_api_ref IS NULL")
    op.alter_column(
        'service',
        'has_api_ref',
        existing_type=sa.BOOLEAN(),
        nullable=False,
        server_default=sa.text('false'),
    )
