from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LineItemOut(BaseModel):
    """Line item representation returned by the API."""

    id: int = Field(..., description="Database ID of the line item")
    description: str = Field(..., description="Description of the work or material")
    quantity: Optional[float] = Field(None, description="Quantity for the line item")
    unit: Optional[str] = Field(None, description="Original unit as parsed from the invoice")
    unit_price: Optional[float] = Field(None, description="Unit price for the item")
    total_price: Optional[float] = Field(None, description="Total price for the item")
    currency: Optional[str] = Field(None, description="Currency code for this line item, e.g., USD")

    category: Optional[str] = Field(None, description="Inferred category")
    normalized_unit: Optional[str] = Field(None, description="Standardized unit")
    normalized_quantity: Optional[float] = Field(None, description="Standardized quantity")
    normalized_unit_price: Optional[float] = Field(None, description="Standardized unit price")

    tax_amount: Optional[float] = Field(
        None, description="Extracted or derived tax amount for this line item (if available)"
    )
    flagged_high_value: bool = Field(False, description="True if total meets or exceeds the high-value threshold")


class InvoiceOut(BaseModel):
    """Invoice header with line items."""

    id: str = Field(..., description="Invoice ID (UUID)")
    vendor_name: Optional[str] = Field(None, description="Vendor or contractor name")
    invoice_number: Optional[str] = Field(None, description="Vendor's invoice number")
    invoice_date: Optional[date] = Field(None, description="Invoice date in ISO format")
    currency: Optional[str] = Field(None, description="Currency code, e.g., USD")

    subtotal: Optional[float] = Field(None, description="Subtotal amount")
    tax: Optional[float] = Field(None, description="Tax amount")
    total: Optional[float] = Field(None, description="Total amount")
    grand_total: Optional[float] = Field(None, description="Grand total amount")

    status: str = Field(..., description="Current invoice status")

    line_items: List[LineItemOut] = Field(default_factory=list, description="Line items associated with invoice")


class UploadResponse(BaseModel):
    """Response for invoice upload."""

    invoice_id: str = Field(..., description="Created invoice ID")


class InvoiceListItem(BaseModel):
    """Invoice list summary item."""

    id: str
    vendor_name: Optional[str]
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    total: Optional[float]
    grand_total: Optional[float]
    created_at: Optional[str]


class InvoiceListResponse(BaseModel):
    """Paginated list of invoices."""

    items: List[InvoiceListItem]
    total: int
    limit: int
    offset: int


class LineItemUpdate(BaseModel):
    """Fields allowed to update for a line item."""

    id: int = Field(..., description="Line item id to update")
    description: Optional[str] = Field(None, description="New description")
    quantity: Optional[float] = Field(None, description="New quantity")
    unit: Optional[str] = Field(None, description="New unit")
    unit_price: Optional[float] = Field(None, description="New unit price")
    total_price: Optional[float] = Field(None, description="New total price")
    category: Optional[str] = Field(None, description="New category")


class ValidateRequest(BaseModel):
    """User-provided corrections for an invoice and its line items."""

    header_updates: Dict[str, Any] = Field(
        default_factory=dict,
        description="Invoice header fields to update; allowed keys: vendor_name, invoice_number, invoice_date, currency, subtotal, tax, total, grand_total",
    )
    line_item_updates: List[LineItemUpdate] = Field(
        default_factory=list, description="List of line item updates by id"
    )
    comment: Optional[str] = Field(None, description="Optional user comment explaining the corrections")


class ValidateResponse(BaseModel):
    """Return the updated invoice after validation edits have been applied."""

    invoice: InvoiceOut
