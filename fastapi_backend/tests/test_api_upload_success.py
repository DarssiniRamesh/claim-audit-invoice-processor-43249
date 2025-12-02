import os
from fastapi.testclient import TestClient

# Ensure tests use an isolated SQLite DB file before importing the app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_upload_api.db"

from src.api.main import app  # noqa: E402
from src.services.extraction import pdf_extractor  # noqa: E402


def test_upload_persists_invoice_success(monkeypatch):
    """
    Integration test: POST /api/invoices/upload
    - Stubs PDF extraction to return deterministic text
    - Verifies 201 response and invoice_id returned
    - Verifies GET /api/invoices/{id} returns persisted invoice with line items
    """

    sample_text = """
    ACME Restoration LLC
    Invoice #: INV-2001
    Invoice Date: 03/15/2025
    Subtotal: $1,200.50
    Tax: $99.50
    Grand Total: $1,300.00
    Labor - Technician - qty 10 hr @ $50.00 = $500.00
    Fans rental   3   day   25.00   75.00
    Discount - ($25.00)
    """.strip()

    async def fake_extract_text(self, data: bytes) -> str:  # type: ignore[no-redef]
        return sample_text

    # Monkeypatch the asynchronous extractor method
    monkeypatch.setattr(pdf_extractor.PDFExtractor, "extract_text", fake_extract_text, raising=True)

    with TestClient(app) as client:
        files = {"file": ("invoice.pdf", b"%PDF-1.4\n%fake_pdf", "application/pdf")}
        resp = client.post("/api/invoices/upload", files=files)

        assert resp.status_code == 201, resp.text
        payload = resp.json()
        assert "invoice_id" in payload
        invoice_id = payload["invoice_id"]

        # Fetch the invoice and validate structure
        resp_get = client.get(f"/api/invoices/{invoice_id}")
        assert resp_get.status_code == 200, resp_get.text
        data = resp_get.json()
        assert data["id"] == invoice_id
        # currency propagated; at least the two positive items persisted (discount skipped)
        assert isinstance(data.get("line_items"), list)
        assert len(data["line_items"]) >= 2
        # Check one known line
        li0 = next((li for li in data["line_items"] if "Labor - Technician" in li["description"]), None)
        assert li0 is not None
        assert abs((li0.get("unit_price") or 0) - 50.0) < 0.001
