# FastAPI Backend

Backend API for the Claim Audit Invoice Processor:
- File upload, PDF extraction, normalization
- Audit rules and findings persistence
- Invoices listing, retrieval, validation
- Pricing benchmarks

## Setup

1) Install dependencies (recommended in a virtual environment):
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt

2) Initialize and run the server:
   uvicorn src.api.main:app --host 0.0.0.0 --port 8000

- On first startup, the app will create the SQLite database (./data/app.db) and seed benchmarks if empty.

## API Docs

- Live Swagger UI: http://localhost:8000/docs
- Live OpenAPI JSON: http://localhost:8000/openapi.json

## Regenerate and Persist OpenAPI Specification

You can generate the OpenAPI specification file (interfaces/openapi.json) directly from the FastAPI app:

   python -m src.api.generate_openapi

This writes the current API schema to:
- interfaces/openapi.json

## Primary Endpoints

- Health
  - GET /  — Simple health check

- Invoices
  - POST /api/invoices/upload  — Upload invoice PDF (multipart/form-data)
  - GET  /api/invoices/{invoice_id}  — Get invoice header + line items
  - GET  /api/invoices  — List with filters (q, vendor_name, invoice_number, date_from, date_to, limit, offset)
  - GET  /api/invoices/{invoice_id}/audit  — Run audit rules and return findings
  - PUT  /api/invoices/{invoice_id}/validate  — Apply user validation edits

- Benchmarks
  - GET /api/benchmarks  — Retrieve pricing benchmarks
