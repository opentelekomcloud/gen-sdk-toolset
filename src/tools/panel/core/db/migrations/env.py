"""Alembic environment for the panel PostgreSQL schema.

The database URL is resolved in this order:

1. ``sqlalchemy.url`` set programmatically on the Alembic config
   (used by tests to point at a throwaway PostgreSQL instance);
2. application settings (``DATABASE__URL`` env var / ``.env`` / TOML).

No engine is created at import time: offline mode renders SQL from the URL
alone, and online mode builds the engine only when migrations actually run.
"""

from logging.config import fileConfig

from alembic import context

from tools.panel.core.db import models  # noqa: F401  (populates Base.metadata)
from tools.panel.core.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured

    from tools.config import load_settings

    return load_settings().database.url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: render SQL without a DBAPI."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode: connect and apply."""
    from sqlalchemy import create_engine

    connectable = create_engine(_database_url())
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
