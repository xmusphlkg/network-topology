from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import Settings
from .db_models import Base

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_database(settings: Settings) -> async_sessionmaker[AsyncSession]:
    global engine, SessionLocal
    url = settings.sqlalchemy_url()
    engine_kwargs: dict[str, object] = {
        "echo": settings.db_echo,
        "pool_pre_ping": True,
    }
    if url.startswith("mysql+aiomysql://"):
        engine_kwargs["pool_recycle"] = 1800
        engine_kwargs["connect_args"] = {"connect_timeout": settings.mysql_connect_timeout_sec}
    engine = create_async_engine(url, **engine_kwargs)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    return SessionLocal


async def create_tables() -> None:
    if engine is None:
        raise RuntimeError("Database engine is not initialized")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_database() -> None:
    global engine, SessionLocal
    if engine is not None:
        await engine.dispose()
    engine = None
    SessionLocal = None


async def get_session() -> AsyncIterator[AsyncSession]:
    if SessionLocal is None:
        raise RuntimeError("Database session maker is not initialized")
    async with SessionLocal() as session:
        yield session
