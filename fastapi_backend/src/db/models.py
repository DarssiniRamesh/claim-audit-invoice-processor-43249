from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


class Severity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _uuid_str() -> str:
    return str(uuid.uuid4())


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    invoice_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True, index=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    subtotal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tax: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    grand_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="uploaded")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )
    raw: Mapped[Optional["InvoiceRaw"]] = relationship(
        back_populates="invoice", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    findings: Mapped[list["AuditFinding"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )
    validations: Mapped[list["ValidationEdit"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_invoices_vendor_name", "vendor_name"),
        Index("ix_invoices_created_at", "created_at"),
    )


class InvoiceRaw(Base):
    __tablename__ = "invoice_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), unique=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="raw")


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    normalized_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    normalized_quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    normalized_unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    flagged_high_value: Mapped[bool] = mapped_column(Boolean, default=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="line_items")

    __table_args__ = (
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_qty_non_negative"),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="ck_unit_price_non_negative"),
        CheckConstraint("total_price IS NULL OR total_price >= 0", name="ck_total_non_negative"),
    )


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    min_price: Mapped[float] = mapped_column(Float, nullable=False)
    max_price: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("ix_benchmarks_cat_unit", "category", "unit", unique=True),)


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    line_item_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("line_items.id", ondelete="SET NULL"), nullable=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), default=Severity.WARNING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="findings")


class ValidationEdit(Base):
    __tablename__ = "validation_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    line_item_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("line_items.id", ondelete="SET NULL"), nullable=True)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="validations")
