from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.core.config import get_settings

# Shared declarative base for ORM models
Base = declarative_base()
logger = logging.getLogger("app.db")

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
        logger.debug("Ensured SQLite directory: %s", db_dir)


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
    """Create database tables if they don't exist and apply lightweight migrations for SQLite."""
    from src.db import models  # Import models so metadata is populated

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

        # Lightweight SQLite migrations (non-destructive: add missing columns)
        url = _settings.DATABASE_URL
        if url.startswith("sqlite+aiosqlite:///"):
            def _apply_sqlite_migrations_sync(sconn) -> None:
                # Helper to check if a column exists
                def _has_column(table: str, column: str) -> bool:
                    rows = sconn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
                    return any(r[1] == column for r in rows)

                # Add currency column to line_items if missing
                if not _has_column("line_items", "currency"):
                    sconn.exec_driver_sql("ALTER TABLE line_items ADD COLUMN currency VARCHAR(10)")
                    try:
                        # Best-effort log via print since we're in sync context
                        print("[DB MIGRATION] Added 'currency' column to 'line_items'")
                    except Exception:
                        pass

            await conn.run_sync(_apply_sqlite_migrations_sync)
            logger.debug("SQLite lightweight migrations applied (if needed).")
