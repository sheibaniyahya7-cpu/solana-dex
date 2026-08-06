"""
Alembic environment configuration.
Supports both online (async) and offline migration modes.
Auto-discovers all SQLAlchemy models via the models __init__.py.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ─── Make the app importable from alembic/ ────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import all models so Alembic can detect schema changes
from app.database.base import Base, metadata  # noqa: E402
import app.database.models  # noqa: E402, F401 — registers all models

from app.core.config import settings  # noqa: E402

# ─── Alembic Config ───────────────────────────────────────────────────────────
config = context.config

# Inject real DB URL from app settings (sync driver for Alembic)
sync_url = settings.DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)
config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for --autogenerate support
target_metadata = metadata


# ─── Offline Mode ─────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Run migrations without a DB connection.
    Produces SQL scripts for manual review/application.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ─── Online Mode (sync wrapper around async engine) ───────────────────────────

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
        # Render CREATE SCHEMA IF NOT EXISTS for the "dex" schema
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def include_object(object, name, type_, reflected, compare_to):
    """Only migrate objects in the 'dex' schema (skip pg_catalog etc.)"""
    if type_ == "table" and object.schema not in (None, "dex"):
        return False
    return True


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a sync connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ─── Entry point ──────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
