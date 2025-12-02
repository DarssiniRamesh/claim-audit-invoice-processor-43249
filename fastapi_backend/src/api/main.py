from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.benchmarks import router as benchmarks_router
from src.api.routers.invoices import router as invoices_router
from src.core.config import get_settings
from src.db.seed.seed_benchmarks import seed_benchmarks_if_empty
from src.db.session import get_session, init_db

settings = get_settings()

openapi_tags = [
    {"name": "Invoices", "description": "Upload, retrieve, validate, list invoices"},
    {"name": "Benchmarks", "description": "Retrieve pricing benchmarks"},
    {"name": "Health", "description": "Service status"},
]

app = FastAPI(
    title="Claim Audit Invoice Processor API",
    description="Backend API for PDF extraction, normalization, audit rules, and data services.",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

# CORS: allow frontend at localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize database and seed benchmark data on startup."""
    await init_db()
    # Seed benchmarks if empty
    async for session in get_session():
        await seed_benchmarks_if_empty(session)


@app.get("/", tags=["Health"], summary="Health check")
def health_check():
    """Simple health check endpoint."""
    return {"message": "Healthy"}


# Routers
app.include_router(invoices_router, prefix="/api/invoices", tags=["Invoices"])
app.include_router(benchmarks_router, prefix="/api/benchmarks", tags=["Benchmarks"])
