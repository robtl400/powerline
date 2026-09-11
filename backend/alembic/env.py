import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db import Base
import app.models  # noqa: F401 — ensures all models are registered on Base.metadata

config = context.config
# ConfigParser interpolates %, which is legal in a URL-encoded password.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Session-level advisory lock key: concurrent `alembic upgrade` runners queue
# behind whichever one holds it.
MIGRATION_LOCK_ID = 0x706F_7765_726C_6E00


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_server_default=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    connection.exec_driver_sql(f"SELECT pg_advisory_lock({MIGRATION_LOCK_ID})")
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_server_default=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    connection.exec_driver_sql(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})")
    connection.commit()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
