"""
Alembic environment.

Two ways in:
- The app (app.db.session.init_db) passes its own connection in
  `config.attributes["connection"]`, so migrations use the app's engine and settings.
- The `alembic` CLI (run from backend/) connects using DATABASE_URL from app settings.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.models.base import Base
from app.models import pr, suggestion  # noqa: F401 - registers the tables on Base

config = context.config
target_metadata = Base.metadata


def run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things in place; batch mode recreates the table instead
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
        return

    # CLI use: keep the CLI's own logging setup (the app configures JSON logging itself)
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as connection:
        run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
