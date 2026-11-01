"""Async SQLAlchemy engine and session management.

The same models run on SQLite (zero-configuration default) and PostgreSQL
(``DATABASE_URL=postgresql+asyncpg://...``) because every column type used is
portable across both backends.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalise_database_url(url: str) -> str:
    """Map common PostgreSQL DSNs onto the asyncpg driver."""
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


_settings = get_settings()

engine = create_async_engine(
    normalise_database_url(_settings.database_url),
    echo=False,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Create tables that do not exist yet.

    Schema evolution for production deployments is handled by Alembic
    (``alembic upgrade head``); this keeps a fresh checkout runnable.
    """
    from app import models  # noqa: F401  (populates Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    await engine.dispose()
