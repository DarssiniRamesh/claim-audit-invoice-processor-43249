from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Benchmark
from src.db.session import get_session

router = APIRouter()


class BenchmarkOut(BaseModel):
    """Benchmark range for a given category and unit."""

    id: int = Field(..., description="Benchmark ID")
    category: str = Field(..., description="Category name")
    unit: str = Field(..., description="Unit")
    min_price: float = Field(..., description="Minimum unit price")
    max_price: float = Field(..., description="Maximum unit price")


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[BenchmarkOut],
    summary="Get pricing benchmarks",
    description="Returns current benchmark ranges by category and unit.",
)
async def get_benchmarks(session: AsyncSession = Depends(get_session)) -> List[BenchmarkOut]:
    """Return all benchmark ranges."""
    rows = (await session.execute(select(Benchmark))).scalars().all()
    return [
        BenchmarkOut(
            id=b.id,
            category=b.category,
            unit=b.unit,
            min_price=b.min_price,
            max_price=b.max_price,
        )
        for b in rows
    ]
