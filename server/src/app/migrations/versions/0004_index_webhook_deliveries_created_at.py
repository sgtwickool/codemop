"""index webhook_deliveries.created_at

Deliveries older than a week are pruned on every webhook, which needs this index to stay cheap.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-07 13:40:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_webhook_deliveries_created_at', 'webhook_deliveries', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_webhook_deliveries_created_at', table_name='webhook_deliveries')
