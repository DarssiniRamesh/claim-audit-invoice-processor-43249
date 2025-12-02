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


class AuditReport(BaseModel):
    """Audit report for an invoice."""

    invoice_id: str = Field(..., description="Invoice ID")
    findings: List[AuditFindingOut] = Field(default_factory=list, description="List of findings")
