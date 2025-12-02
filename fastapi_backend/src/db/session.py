from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.core.config import get_settings

# Shared declarative base for ORM models
Base = declarative_base()

_settings = get_settings()


def _ensure_sqlite_dir(url: str) -> None:
    """Create parent directory for SQLite file if using a file-based SQLite URL."""
    # Only handle sqlite+aiosqlite URLs with relative path file.
    if url.startswith("sqlite+aiosqlite:///"):
        path_part = url.replace("sqlite+aiosqlite:///", "", 1)
        # For relative paths like ./data/app.db
        db_path = Path(path_part)
        if not db_path.is_absolute():
            db_path = Path.cwd() / path_part
        db_dir = db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(_settings.DATABASE_URL)

# Create async engine and sessionmaker
engine = create_async_engine(_settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False, autocommit=False
)


# PUBLIC_INTERFACE
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session for request-scoped DB operations."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # Explicit close for safety
            await session.close()


# PUBLIC_INTERFACE
async def init_db() -> None:
    """Create database tables if they don't exist."""
    from src.db import models  # Import models so metadata is populated

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
