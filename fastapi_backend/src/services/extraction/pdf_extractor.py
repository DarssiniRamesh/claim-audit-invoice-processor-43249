from __future__ import annotations

import asyncio
import io
from typing import Optional

from src.core.config import get_settings

_settings = get_settings()


class PDFExtractionError(Exception):
    """Raised when PDF extraction fails."""


class PDFExtractor:
    """Extracts raw text from PDFs using pdfplumber (primary) with PyPDF2 fallback."""

    def __init__(self, timeout_seconds: Optional[int] = None) -> None:
        self.timeout_seconds = timeout_seconds or _settings.PDF_EXTRACTION_TIMEOUT

    async def _extract_with_pdfplumber(self, data: bytes) -> str:
        def _sync_extract() -> str:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text() or ""
                    text_parts.append(txt)
            return "\n".join(text_parts).strip()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_extract)

    async def _extract_with_pypdf2(self, data: bytes) -> str:
        def _sync_extract() -> str:
            from PyPDF2 import PdfReader

            text_parts = []
            reader = PdfReader(io.BytesIO(data))
            for page in reader.pages:
                txt = page.extract_text() or ""
                text_parts.append(txt)
            return "\n".join(text_parts).strip()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_extract)

    # PUBLIC_INTERFACE
    async def extract_text(self, data: bytes) -> str:
        """Extract text from a PDF, enforcing a timeout and using fallback strategy."""
        try:
            text = await asyncio.wait_for(self._extract_with_pdfplumber(data), timeout=self.timeout_seconds)
            if text:
                return text
        except Exception:
            # Fall through to PyPDF2
            pass

        try:
            text = await asyncio.wait_for(self._extract_with_pypdf2(data), timeout=self.timeout_seconds)
            if text:
                return text
        except Exception as e:
            raise PDFExtractionError(f"PDF extraction failed: {e}") from e

        raise PDFExtractionError("No text could be extracted from PDF.")
