import os
from typing import List

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment with safe defaults."""

    # Database URL: async SQLite by default, stored in ./data/app.db
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db")

    # CORS allowed origins
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

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
