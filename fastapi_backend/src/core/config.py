import os
from typing import List

from dotenv import load_dotenv

load_dotenv()


# Default CORS origins allowed when no environment variables are provided.
DEFAULT_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://vscode-internal-20803-beta.beta01.cloud.kavia.ai:3000",
]


class Settings:
    """Application settings loaded from environment with safe defaults."""

    # Database URL: async SQLite by default, stored in ./data/app.db
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db")

    # Additional single frontend origin (convenience). If set, it's appended to defaults.
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "").strip()

    # Build CORS origins:
    # - If CORS_ORIGINS is set, use it verbatim (comma-separated list).
    # - Otherwise, use DEFAULT_CORS_ORIGINS plus FRONTEND_ORIGIN (if provided).
    _cors_env = os.getenv("CORS_ORIGINS", "")
    if _cors_env.strip():
        _origins_raw = [o.strip() for o in _cors_env.split(",") if o.strip()]
    else:
        _origins_raw = list(DEFAULT_CORS_ORIGINS)
        if FRONTEND_ORIGIN:
            _origins_raw.append(FRONTEND_ORIGIN)

    # Deduplicate (preserve order) and sanitize; avoid empty entries.
    _seen = set()
    _dedup: List[str] = []
    for o in _origins_raw:
        if o and o not in _seen:
            _dedup.append(o)
            _seen.add(o)

    # Final list of allowed origins (no wildcard by default).
    CORS_ORIGINS: List[str] = _dedup

    # Max upload size (bytes). Default: 20 MB
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", str(20 * 1024 * 1024)))

    # PDF extraction timeout (seconds)
    PDF_EXTRACTION_TIMEOUT: int = int(os.getenv("PDF_EXTRACTION_TIMEOUT", "30"))

    # Environment name for logging/diagnostics
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")


# PUBLIC_INTERFACE
def get_settings() -> Settings:
    """Return application settings."""
    return Settings()
