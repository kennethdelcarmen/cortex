"""Alembic environment for the async SQLite backend."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from cortex_backend.attachments import models as _attachment_models  # noqa: F401
from cortex_backend.auth.models import Base
from cortex_backend.config import Settings
from cortex_backend.files import models as _file_models  # noqa: F401
from cortex_backend.logs import models as _activity_log_models  # noqa: F401
from cortex_backend.memory import models as _memory_models  # noqa: F401
from cortex_backend.tasks import models as _task_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Build the migration URL from the same typed settings as the application."""

    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{settings.database_path}"


def run_migrations_offline() -> None:
    """Run migrations without creating a live database connection."""

    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure Alembic against a synchronous connection facade."""

    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations through SQLAlchemy's async SQLite driver."""

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run online migrations from the Alembic command entry point."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
