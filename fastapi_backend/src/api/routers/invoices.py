from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import UUID4
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import get_settings
from src.db.models import Invoice, InvoiceRaw, LineItem, ValidationEdit
from src.db.session import get_session
from src.schemas.audit import AuditReport, AuditFindingOut
from src.schemas.invoice import (
    InvoiceListItem,
    InvoiceListResponse,
    InvoiceOut,
    UploadResponse,
    ValidateRequest,
    ValidateResponse,
    LineItemOut,
)
from src.services.audit.engine import AuditEngine
from src.services.extraction.pdf_extractor import PDFExtractor, PDFExtractionError
from src.services.normalization.normalizer import Normalizer

router = APIRouter()


def _to_invoice_out(inv: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=inv.id,
        vendor_name=inv.vendor_name,
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        currency=inv.currency,
        subtotal=inv.subtotal,
        tax=inv.tax,
        total=inv.total,
        grand_total=inv.grand_total,
        status=inv.status,
        line_items=[
            LineItemOut(
                id=li.id,
                description=li.description,
                quantity=li.quantity,
                unit=li.unit,
                unit_price=li.unit_price,
                total_price=li.total_price,
                category=li.category,
                normalized_unit=li.normalized_unit,
                normalized_quantity=li.normalized_quantity,
                normalized_unit_price=li.normalized_unit_price,
                flagged_high_value=li.flagged_high_value,
            )
            for li in inv.line_items
        ],
    )


# PUBLIC_INTERFACE
@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload invoice PDF",
    description="Accepts a PDF file, extracts text, normalizes content, persists to DB, and returns the created invoice ID.",
    responses={
        201: {"description": "Invoice created"},
        400: {"description": "Invalid file"},
        413: {"description": "File too large"},
        422: {"description": "Unprocessable PDF"},
    },
)
async def upload_invoice(
    file: UploadFile = File(..., description="Invoice PDF to upload"),
    session: AsyncSession = Depends(get_session),
) -> UploadResponse:
    """Upload a PDF invoice for extraction and normalization, persist to DB, return invoice_id."""
    settings = get_settings()
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large.")

    extractor = PDFExtractor(timeout_seconds=settings.PDF_EXTRACTION_TIMEOUT)
    try:
        raw_text = await extractor.extract_text(data)
    except PDFExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Parse normalized header and items
    normalizer = Normalizer()
    header, items = normalizer.parse_invoice(raw_text)

    # Persist entities
    inv = Invoice(
        vendor_name=header.get("vendor_name"),
        invoice_number=header.get("invoice_number"),
        invoice_date=header.get("invoice_date"),
        currency=header.get("currency"),
        subtotal=header.get("subtotal"),
        tax=header.get("tax"),
        total=header.get("total"),
        grand_total=header.get("grand_total"),
        status="uploaded",
    )
    session.add(inv)
    await session.flush()  # Get inv.id

    raw = InvoiceRaw(invoice_id=inv.id, raw_text=raw_text, meta={"filename": file.filename})
    session.add(raw)

    for it in items:
        li = LineItem(
            invoice_id=inv.id,
            description=it["description"],
            quantity=it.get("quantity"),
            unit=it.get("unit"),
            unit_price=it.get("unit_price"),
            total_price=it.get("total_price"),
            category=it.get("category"),
            normalized_unit=it.get("normalized_unit"),
            normalized_quantity=it.get("normalized_quantity"),
            normalized_unit_price=it.get("normalized_unit_price"),
            flagged_high_value=bool(it.get("flagged_high_value", False)),
        )
        session.add(li)

    await session.commit()
    return UploadResponse(invoice_id=inv.id)


# PUBLIC_INTERFACE
@router.get(
    "/{invoice_id}",
    response_model=InvoiceOut,
    summary="Get invoice by ID",
    description="Return invoice header and associated line items.",
    responses={404: {"description": "Invoice not found"}},
)
async def get_invoice(
    invoice_id: UUID4,
    session: AsyncSession = Depends(get_session),
) -> InvoiceOut:
    """Return invoice details and line items."""
    inv = (
        await session.execute(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(Invoice.id == str(invoice_id))
        )
    ).scalars().first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return _to_invoice_out(inv)


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=InvoiceListResponse,
    summary="List invoices",
    description="Supports filtering by vendor name, invoice number, date range, and free-text search; includes pagination.",
)
async def list_invoices(
    q: Optional[str] = Query(None, description="Free-text search across vendor name and invoice number"),
    vendor_name: Optional[str] = Query(None, description="Filter by vendor name"),
    invoice_number: Optional[str] = Query(None, description="Filter by invoice number"),
    date_from: Optional[date] = Query(None, description="Start date for invoice_date"),
    date_to: Optional[date] = Query(None, description="End date for invoice_date"),
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
) -> InvoiceListResponse:
    """List invoices with filters and pagination."""
    stmt = select(Invoice)
    count_stmt = select(func.count(Invoice.id))

    conditions = []
    if q:
        conditions.append(or_(Invoice.vendor_name.ilike(f"%{q}%"), Invoice.invoice_number.ilike(f"%{q}%")))
    if vendor_name:
        conditions.append(Invoice.vendor_name.ilike(f"%{vendor_name}%"))
    if invoice_number:
        conditions.append(Invoice.invoice_number.ilike(f"%{invoice_number}%"))
    if date_from:
        conditions.append(Invoice.invoice_date >= date_from)
    if date_to:
        conditions.append(Invoice.invoice_date <= date_to)

    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)

    stmt = stmt.order_by(Invoice.created_at.desc()).offset(offset).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()

    items = [
        InvoiceListItem(
            id=r.id,
            vendor_name=r.vendor_name,
            invoice_number=r.invoice_number,
            invoice_date=r.invoice_date,
            total=r.total,
            grand_total=r.grand_total,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return InvoiceListResponse(items=items, total=total, limit=limit, offset=offset)


# PUBLIC_INTERFACE
@router.get(
    "/{invoice_id}/audit",
    response_model=AuditReport,
    summary="Run and return audit findings for an invoice",
    description="Applies audit rules and persists findings. Returns structured findings and severity.",
)
async def get_invoice_audit(
    invoice_id: UUID4,
    session: AsyncSession = Depends(get_session),
) -> AuditReport:
    """Run the audit rules for the given invoice and return the findings."""
    inv = (
        await session.execute(select(Invoice).where(Invoice.id == str(invoice_id)))
    ).scalars().first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    engine = AuditEngine(session)
    findings = await engine.run(str(invoice_id))
    out = [
        AuditFindingOut(
            id=f.id,
            code=f.code,
            message=f.message,
            severity=f.severity.value if hasattr(f.severity, "value") else str(f.severity),
            line_item_id=f.line_item_id,
        )
        for f in findings
    ]
    return AuditReport(invoice_id=str(invoice_id), findings=out)


# PUBLIC_INTERFACE
@router.put(
    "/{invoice_id}/validate",
    response_model=ValidateResponse,
    summary="Apply user validation edits to an invoice",
    description="Accepts header and line-item corrections; persists them and returns the updated invoice.",
)
async def validate_invoice(
    invoice_id: UUID4,
    payload: ValidateRequest,
    session: AsyncSession = Depends(get_session),
) -> ValidateResponse:
    """Persist user corrections to the invoice and return the updated invoice."""
    inv = (
        await session.execute(select(Invoice).where(Invoice.id == str(invoice_id)))
    ).scalars().first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    allowed_header_fields = {
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "currency",
        "subtotal",
        "tax",
        "total",
        "grand_total",
    }

    # Header updates
    for k, v in payload.header_updates.items():
        if k not in allowed_header_fields:
            raise HTTPException(status_code=400, detail=f"Invalid header field: {k}")
        old = getattr(inv, k, None)
        # Convert date string to date
        if k == "invoice_date" and isinstance(v, str):
            try:
                v = datetime.fromisoformat(v).date()
            except Exception:
                raise HTTPException(status_code=400, detail="invoice_date must be ISO date (YYYY-MM-DD).")
        setattr(inv, k, v)

        # Save validation edit
        session.add(
            ValidationEdit(
                invoice_id=inv.id,
                line_item_id=None,
                field=k,
                old_value=str(old) if old is not None else None,
                new_value=str(v) if v is not None else None,
                reason=payload.comment,
            )
        )

    # Line item updates
    for upd in payload.line_item_updates:
        li = (
            await session.execute(select(LineItem).where(LineItem.id == upd.id, LineItem.invoice_id == inv.id))
        ).scalars().first()
        if not li:
            raise HTTPException(status_code=400, detail=f"Line item not found: {upd.id}")

        update_fields = upd.model_dump(exclude_unset=True)
        update_fields.pop("id", None)

        for k, v in update_fields.items():
            old = getattr(li, k, None)
            setattr(li, k, v)

            session.add(
                ValidationEdit(
                    invoice_id=inv.id,
                    line_item_id=li.id,
                    field=k,
                    old_value=str(old) if old is not None else None,
                    new_value=str(v) if v is not None else None,
                    reason=payload.comment,
                )
            )

        # Recalculate total if qty and unit_price provided and total_price not explicitly set
        if "quantity" in update_fields or "unit_price" in update_fields:
            if li.quantity is not None and li.unit_price is not None and "total_price" not in update_fields:
                li.total_price = round(li.quantity * li.unit_price, 2)

    await session.commit()

    # Return updated invoice
    inv = (
        await session.execute(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(Invoice.id == str(invoice_id))
        )
    ).scalars().first()
    return ValidateResponse(invoice=_to_invoice_out(inv))
