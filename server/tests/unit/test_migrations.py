"""
Tests for the database migrations.

Each test uses its own SQLite database, separate from the one the rest of the suite shares.
"""
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.db.session import alembic_config, alembic_connection, init_db, BASELINE_REVISION
from app.models.base import Base


@pytest.fixture
def fresh_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/migrations.db")
    yield engine
    engine.dispose()


def _run(engine, fn, revision):
    with alembic_connection(engine) as (config, _):
        fn(config, revision)


def _current_revision(engine):
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _head_revision():
    from alembic.script import ScriptDirectory
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def test_migrations_match_models(fresh_engine):
    """Running every migration produces exactly the schema the models describe."""
    init_db(fresh_engine)

    with fresh_engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []


def test_database_from_before_migrations_is_upgraded(fresh_engine):
    """A database created by the old create_all() keeps its data and is brought up to date."""
    # Recreate the pre-migrations state: baseline tables, no migration history
    _run(fresh_engine, command.upgrade, BASELINE_REVISION)
    with fresh_engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
        connection.execute(text(
            "INSERT INTO prs (github_id, repo_name, repo_full_name, branch, author, title, "
            "status, github_url, diff_url) VALUES (7, 'repo', 'owner/repo', 'main', 'me', "
            "'Old PR', 'opened', 'https://github.com/owner/repo/pull/7', "
            "'https://github.com/owner/repo/pull/7.diff')"
        ))

    init_db(fresh_engine)

    assert _current_revision(fresh_engine) == _head_revision()
    with fresh_engine.connect() as connection:
        titles = connection.execute(text("SELECT title FROM prs")).scalars().all()
    assert titles == ["Old PR"]


def test_init_db_is_idempotent(fresh_engine):
    init_db(fresh_engine)
    init_db(fresh_engine)

    assert _current_revision(fresh_engine) == _head_revision()


def test_downgrade_to_base_removes_everything(fresh_engine):
    init_db(fresh_engine)

    _run(fresh_engine, command.downgrade, "base")

    assert inspect(fresh_engine).get_table_names() == ["alembic_version"]
