"""Alembic environment — URL from CALLSCOPE_DATABASE_URL / settings (sync)."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from callscope.config import get_settings
from callscope.db.models import Base
from callscope.db.urls import to_async_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    raw = (
        os.environ.get("CALLSCOPE_DATABASE_URL")
        or os.environ.get("CALLSCOPE_TEST_DATABASE_URL")
        or get_settings().database_url
    )
    # Sync migrations use the same psycopg driver URL.
    return to_async_url(raw)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
