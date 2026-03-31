from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _engine_kwargs() -> dict:
    """Return dialect-appropriate keyword arguments for :func:`create_async_engine`.

    * **SQLite** – aiosqlite manages its own connection-level locking; extra
      pool kwargs are neither needed nor supported.
    * **PostgreSQL** – asyncpg benefits from a real connection pool with
      pre-ping so stale connections are detected before they cause query
      failures.
    """
    if settings.db_dialect == "postgresql":
        return {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_pre_ping": True,
        }
    return {}


engine = create_async_engine(settings.DATABASE_URL, echo=False, **_engine_kwargs())
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
# Alias used by modules that need a session outside of a request context
# (e.g. the IP blocker middleware and background tasks).
AsyncSessionLocal = async_session


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    """Create tables if they don't exist.

    In production, prefer running ``alembic upgrade head`` before starting the
    server so that schema changes are applied incrementally and tracked.
    This fallback keeps the development workflow simple (no extra step needed).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
