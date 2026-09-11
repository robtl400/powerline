"""Database engine, session factory and the declarative base.

The pool is sized explicitly rather than left at SQLAlchemy's default of five
connections with ten overflow: a streaming CSV export holds one connection for
the length of the download and the dashboard and analytics tiles issue several
aggregates per page load, so a default-sized pool queues ordinary requests
behind one report. pool_pre_ping discards a connection the database has closed
underneath the process — an idle timeout, a failover — instead of handing the
dead one to a request.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
