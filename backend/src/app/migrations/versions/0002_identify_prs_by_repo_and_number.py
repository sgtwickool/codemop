"""identify PRs by repo and number

PR numbers restart at 1 in every repository, but `github_id` (really the PR number)
was unique across the whole table, so PR #1 in one repo overwrote PR #1 in another.

- rename `github_id` to `number`, make it a BIGINT, and make (repo_full_name, number) unique
- make `title` TEXT rather than VARCHAR(512)

Downgrading fails if two repos now have PRs with the same number.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('ix_prs_github_id', table_name='prs')
    with op.batch_alter_table('prs') as batch_op:
        batch_op.alter_column(
            'github_id',
            new_column_name='number',
            type_=sa.BigInteger(),
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'title',
            type_=sa.Text(),
            existing_type=sa.String(length=512),
            existing_nullable=False,
        )
    # Separate batch: on SQLite a constraint on a column renamed in the same batch is lost
    with op.batch_alter_table('prs') as batch_op:
        batch_op.create_unique_constraint('uq_prs_repo_full_name_number', ['repo_full_name', 'number'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('prs') as batch_op:
        batch_op.drop_constraint('uq_prs_repo_full_name_number', type_='unique')
    with op.batch_alter_table('prs') as batch_op:
        batch_op.alter_column(
            'title',
            type_=sa.String(length=512),
            existing_type=sa.Text(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'number',
            new_column_name='github_id',
            type_=sa.Integer(),
            existing_type=sa.BigInteger(),
            existing_nullable=False,
        )
    op.create_index('ix_prs_github_id', 'prs', ['github_id'], unique=True)
