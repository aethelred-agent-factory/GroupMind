"""Alembic configuration file."""

from logging.config import fileConfig
import asyncio
from sqlalchemy import pool
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from alembic import context
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# This is the Alembic Config object, which provides the values of various Alembic directives
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models
from bot.models.database import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    sqlalchemy_url = os.getenv("DATABASE_URL", "postgresql://localhost/groupmind")
    
    # Convert to async URL if needed
    if "postgresql://" in sqlalchemy_url:
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+asyncpg://")

    context.configure(
        url=sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations synchronously."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    sqlalchemy_url = os.getenv("DATABASE_URL", "postgresql://localhost/groupmind")
    
    # Convert to async URL if needed
    if "postgresql://" in sqlalchemy_url:
        sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+asyncpg://")

    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = sqlalchemy_url

    connectable = create_async_engine(
        sqlalchemy_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
