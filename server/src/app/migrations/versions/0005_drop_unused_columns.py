"""drop unused columns

- prs.diff_url: diffs are fetched from the GitHub REST API, so the github.com diff URL
  from the webhook payload is never read
- suggestions.head_sha: a PR's suggestions are always replaced together, so every
  suggestion's head_sha equals its PR's analyzed_sha

Downgrading restores both columns as nullable; their old values aren't recovered.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('prs') as batch_op:
        batch_op.drop_column('diff_url')
    with op.batch_alter_table('suggestions') as batch_op:
        batch_op.drop_column('head_sha')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('suggestions') as batch_op:
        batch_op.add_column(sa.Column('head_sha', sa.String(length=40), nullable=True))
    with op.batch_alter_table('prs') as batch_op:
        batch_op.add_column(sa.Column('diff_url', sa.String(length=512), nullable=True))
