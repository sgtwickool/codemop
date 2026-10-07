"""track analysed commits and webhook deliveries

- prs.head_sha: the PR's latest commit; prs.analyzed_sha: the commit its suggestions are for
- suggestions.head_sha: the commit each suggestion was made for
- webhook_deliveries: processed X-GitHub-Delivery IDs, so redeliveries are ignored
- prs.status now holds the PR's state (open, closed or merged) instead of the last
  webhook action. Existing rows are converted; whether a closed PR was merged isn't
  recorded, so those become "closed" until their next event.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-07 12:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'webhook_deliveries',
        sa.Column('delivery_id', sa.String(length=64), nullable=False),
        sa.Column('event', sa.String(length=64), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('delivery_id', name='uq_webhook_deliveries_delivery_id'),
    )
    op.create_index('ix_webhook_deliveries_id', 'webhook_deliveries', ['id'], unique=False)

    with op.batch_alter_table('prs') as batch_op:
        batch_op.add_column(sa.Column('head_sha', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('analyzed_sha', sa.String(length=40), nullable=True))

    with op.batch_alter_table('suggestions') as batch_op:
        batch_op.add_column(sa.Column('head_sha', sa.String(length=40), nullable=True))

    op.execute(
        "UPDATE prs SET status = CASE WHEN status = 'closed' THEN 'closed' ELSE 'open' END"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # The previous last-action values can't be recovered; open/closed/merged are kept
    with op.batch_alter_table('suggestions') as batch_op:
        batch_op.drop_column('head_sha')

    with op.batch_alter_table('prs') as batch_op:
        batch_op.drop_column('analyzed_sha')
        batch_op.drop_column('head_sha')

    op.drop_index('ix_webhook_deliveries_id', table_name='webhook_deliveries')
    op.drop_table('webhook_deliveries')
