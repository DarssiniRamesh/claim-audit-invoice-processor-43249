from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Benchmark


# PUBLIC_INTERFACE
async def seed_benchmarks_if_empty(session: AsyncSession) -> None:
    """Seed the benchmarks table from local JSON if it's currently empty."""
    count = (await session.execute(select(Benchmark))).scalars().first()
    if count is not None:
        # Already has data
        return

    seed_path = Path(__file__).resolve().parent / "benchmarks.json"
    if not seed_path.exists():
        return

    items = json.loads(seed_path.read_text())
    session.add_all([Benchmark(**item) for item in items])
    await session.commit()
