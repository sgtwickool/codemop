"""baseline schema

The schema as it was created by `Base.metadata.create_all()` before migrations existed.
Databases created that way are stamped at this revision by init_db and upgraded from here.

Revision ID: 0001
Revises:
Create Date: 2026-10-07 11:49:40.342865

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'prs',
        sa.Column('github_id', sa.Integer(), nullable=False),
        sa.Column('repo_name', sa.String(length=255), nullable=False),
        sa.Column('repo_full_name', sa.String(length=255), nullable=False),
        sa.Column('branch', sa.String(length=255), nullable=False),
        sa.Column('author', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('github_url', sa.String(length=512), nullable=False),
        sa.Column('diff_url', sa.String(length=512), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_prs_github_id', 'prs', ['github_id'], unique=True)
    op.create_index('ix_prs_id', 'prs', ['id'], unique=False)
    op.create_index('ix_prs_repo_name', 'prs', ['repo_name'], unique=False)

    op.create_table(
        'suggestions',
        sa.Column('pr_id', sa.Integer(), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('fix', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['pr_id'], ['prs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_suggestions_id', 'suggestions', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_suggestions_id', table_name='suggestions')
    op.drop_table('suggestions')
    op.drop_index('ix_prs_repo_name', table_name='prs')
    op.drop_index('ix_prs_id', table_name='prs')
    op.drop_index('ix_prs_github_id', table_name='prs')
    op.drop_table('prs')
