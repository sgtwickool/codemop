"""richer suggestions

Suggestions now come from the codemop package's review, which reports a severity, a
one-line title and, for multi-line issues, the last line. Existing rows keep NULLs.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-07 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('suggestions') as batch_op:
        batch_op.add_column(sa.Column('end_line', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('severity', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('title', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('suggestions') as batch_op:
        batch_op.drop_column('title')
        batch_op.drop_column('severity')
        batch_op.drop_column('end_line')
