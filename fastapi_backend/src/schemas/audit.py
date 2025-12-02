from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AuditFindingOut(BaseModel):
    """Structured audit finding."""

    id: int = Field(..., description="Finding ID")
    code: str = Field(..., description="Finding code")
    message: str = Field(..., description="Human-readable message")
    severity: str = Field(..., description="Severity level: INFO, WARNING, ERROR")
    line_item_id: Optional[int] = Field(None, description="Related line item id if applicable")


class GeneralAuditSection(BaseModel):
    """General audit section that groups high-level invoice checks and rule-based findings."""

    findings: List[AuditFindingOut] = Field(default_factory=list, description="General audit findings")


class PurchaseLineItemAudit(BaseModel):
    """Per-purchase audit view with tax extraction and validation."""

    line_item_id: int = Field(..., description="Related line item id")
    description: str = Field(..., description="Line item description")
    quantity: Optional[float] = Field(None, description="Quantity")
    unit_price: Optional[float] = Field(None, description="Unit price")
    total_price: Optional[float] = Field(None, description="Total price including any tax")
    currency: Optional[str] = Field(None, description="Currency for the line item")
    tax_amount: Optional[float] = Field(None, description="Extracted or derived tax amount for the line")
    expected_tax: Optional[float] = Field(None, description="Expected tax computed from inferred tax rate and base")
    tax_rate_used: Optional[float] = Field(None, description="Tax rate used to compute expected tax (fraction, e.g. 0.0825)")
    tax_ok: Optional[bool] = Field(None, description="True if extracted tax matches expected tax within tolerance")


class PurchaseAuditSection(BaseModel):
    """Purchase audit section: inferred tax rate and per-line tax validation results."""

    tax_rate_inferred: Optional[float] = Field(None, description="Invoice-level inferred tax rate (fraction)")
    items: List[PurchaseLineItemAudit] = Field(default_factory=list, description="Per-line purchase audit entries")


class AuditReport(BaseModel):
    """Audit report for an invoice with General and Purchase sections."""

    invoice_id: str = Field(..., description="Invoice ID")
    general: GeneralAuditSection = Field(..., description="General audit results")
    purchase: PurchaseAuditSection = Field(..., description="Purchase audit with per-line tax validation")
