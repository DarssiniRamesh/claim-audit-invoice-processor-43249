from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AuditFinding, Benchmark, Invoice, LineItem, Severity


@dataclass
class FindingSpec:
    code: str
    message: str
    severity: Severity
    line_item_id: Optional[int] = None


def _float(x: Optional[float]) -> float:
    return float(x or 0.0)


class AuditEngine:
    """Applies audit rules to an invoice and persists findings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # PUBLIC_INTERFACE
    async def run(self, invoice_id: str) -> List[AuditFinding]:
        """Run audit rules for a specific invoice and persist findings."""
        invoice = (
            await self.session.execute(select(Invoice).where(Invoice.id == invoice_id))
        ).scalars().first()
        if not invoice:
            return []

        items: List[LineItem] = (
            await self.session.execute(select(LineItem).where(LineItem.invoice_id == invoice_id))
        ).scalars().all()

        # Load benchmarks
        benchmarks = (await self.session.execute(select(Benchmark))).scalars().all()

        # Compute findings
        findings_specs: List[FindingSpec] = []
        findings_specs.extend(self._required_fields(invoice))
        findings_specs.extend(self._totals_checks(invoice, items))
        findings_specs.extend(self._high_value_items(items))
        findings_specs.extend(self._benchmark_price_checks(items, benchmarks))

        # Persist: clear existing findings then add
        await self.session.execute(delete(AuditFinding).where(AuditFinding.invoice_id == invoice_id))
        self.session.add_all(
            [
                AuditFinding(
                    invoice_id=invoice_id,
                    line_item_id=fs.line_item_id,
                    code=fs.code,
                    message=fs.message,
                    severity=fs.severity,
                )
                for fs in findings_specs
            ]
        )
        await self.session.commit()

        saved = (
            await self.session.execute(select(AuditFinding).where(AuditFinding.invoice_id == invoice_id))
        ).scalars().all()
        return list(saved)

    def _required_fields(self, invoice: Invoice) -> List[FindingSpec]:
        missing = []
        if not invoice.vendor_name:
            missing.append("vendor_name")
        if not invoice.invoice_number:
            missing.append("invoice_number")
        if not invoice.invoice_date:
            missing.append("invoice_date")
        if not invoice.currency:
            missing.append("currency")

        if missing:
            return [
                FindingSpec(
                    code="REQUIRED_FIELD_MISSING",
                    message=f"Missing required fields: {', '.join(missing)}",
                    severity=Severity.ERROR,
                )
            ]
        return []

    def _totals_checks(self, invoice: Invoice, items: List[LineItem]) -> List[FindingSpec]:
        findings: List[FindingSpec] = []
        sum_items = sum([_float(i.total_price) for i in items])
        subtotal = _float(invoice.subtotal)
        tax = _float(invoice.tax)
        total = _float(invoice.total)
        grand = _float(invoice.grand_total)

        # If subtotal provided, compare to sum of items
        if invoice.subtotal is not None and abs(sum_items - subtotal) > 1.0:
            findings.append(
                FindingSpec(
                    code="SUBTOTAL_MISMATCH",
                    message=f"Subtotal {subtotal:.2f} does not match sum of line items {sum_items:.2f}",
                    severity=Severity.WARNING,
                )
            )

        # If total provided, compare subtotal + tax
        if invoice.total is not None and abs((subtotal + tax) - total) > 1.0:
            findings.append(
                FindingSpec(
                    code="TOTAL_MISMATCH",
                    message=f"Total {total:.2f} != subtotal + tax ({subtotal:.2f} + {tax:.2f})",
                    severity=Severity.WARNING,
                )
            )

        # Compare grand_total to total if both set
        if invoice.grand_total is not None and total and abs(grand - total) > 1.0:
            findings.append(
                FindingSpec(
                    code="GRAND_TOTAL_MISMATCH",
                    message=f"Grand total {grand:.2f} does not match total {total:.2f}",
                    severity=Severity.ERROR,
                )
            )
        return findings

    def _high_value_items(self, items: List[LineItem]) -> List[FindingSpec]:
        findings: List[FindingSpec] = []
        for it in items:
            if _float(it.total_price) >= 500.0:
                findings.append(
                    FindingSpec(
                        code="HIGH_VALUE_LINE_ITEM",
                        message=f"Line item '{it.description[:40]}' total {it.total_price:.2f} exceeds threshold",
                        severity=Severity.WARNING,
                        line_item_id=it.id,
                    )
                )
        return findings

    def _benchmark_price_checks(self, items: List[LineItem], benchmarks: List[Benchmark]) -> List[FindingSpec]:
        findings: List[FindingSpec] = []

        # Build lookup
        bench_map = {(b.category.lower(), b.unit.lower()): b for b in benchmarks}

        for it in items:
            if not it.category or not it.normalized_unit or it.unit_price is None:
                continue
            key = (it.category.lower(), it.normalized_unit.lower())
            b = bench_map.get(key)
            if not b:
                continue
            up = _float(it.unit_price)
            if up < b.min_price:
                findings.append(
                    FindingSpec(
                        code="UNIT_PRICE_BELOW_MIN",
                        message=f"Unit price {up:.2f} below benchmark min {b.min_price:.2f} ({it.category}/{it.normalized_unit})",
                        severity=Severity.WARNING,
                        line_item_id=it.id,
                    )
                )
            elif up > b.max_price:
                findings.append(
                    FindingSpec(
                        code="UNIT_PRICE_ABOVE_MAX",
                        message=f"Unit price {up:.2f} above benchmark max {b.max_price:.2f} ({it.category}/{it.normalized_unit})",
                        severity=Severity.ERROR,
                        line_item_id=it.id,
                    )
                )
        return findings
