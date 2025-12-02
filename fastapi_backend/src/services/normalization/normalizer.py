from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


_UNIT_MAP = {
    "hr": "hour",
    "hrs": "hour",
    "hour": "hour",
    "sqft": "square_foot",
    "ft2": "square_foot",
    "sf": "square_foot",
    "lf": "linear_foot",
    "ft": "linear_foot",
    "day": "day",
    "days": "day",
    "yd3": "cubic_yard",
    "cuyd": "cubic_yard",
}

_CATEGORY_KEYWORDS = {
    "labor": ["labor", "technician", "crew", "hour"],
    "materials": ["material", "sheetrock", "drywall", "lumber", "paint", "sealant"],
    "equipment": ["equipment", "dehumidifier", "air mover", "pump", "fan"],
    "disposal": ["haul", "disposal", "dump", "debris"],
    "mold_remediation": ["mold", "remediation"],
    "water_mitigation": ["water", "mitigation", "extraction", "drying"],
}


def _normalize_unit(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return None
    u = unit.strip().lower()
    return _UNIT_MAP.get(u, u)


def _infer_category(description: str, default: Optional[str] = None) -> Optional[str]:
    d = description.lower()
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(k in d for k in keywords):
            return cat
    return default


def _parse_money(val: str) -> Optional[float]:
    try:
        cleaned = re.sub(r"[^0-9.\-]", "", val)
        if cleaned == "" or cleaned == "." or cleaned == "-":
            return None
        return float(cleaned)
    except Exception:
        return None


def _parse_date(val: str) -> Optional[str]:
    # Attempt common formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(val.strip(), fmt)
            return dt.date().isoformat()
        except Exception:
            continue
    return None


class Normalizer:
    """Parses raw text into an invoice header and line items with normalized values."""

    # PUBLIC_INTERFACE
    def parse_invoice(self, raw_text: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Return (header, items) parsed from raw text."""
        header: Dict[str, Any] = {
            "vendor_name": None,
            "invoice_number": None,
            "invoice_date": None,
            "currency": "USD",
            "subtotal": None,
            "tax": None,
            "total": None,
            "grand_total": None,
        }
        items: List[Dict[str, Any]] = []

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if lines:
            # Take first non-empty line as vendor candidate
            header["vendor_name"] = lines[0][:255]

        # Extract common fields
        patterns = {
            "invoice_number": r"(?:Invoice\s*(?:No\.|#|Number)[:\s]*)([A-Za-z0-9\-]+)",
            "invoice_date": r"(?:Invoice\s*Date|Date)[:\s]*([0-9/\-]{6,10})",
            "subtotal": r"(?:Subtotal)[:\s]*([$€£]?\s*[0-9,.\-]+)",
            "tax": r"(?:Tax)[:\s]*([$€£]?\s*[0-9,.\-]+)",
            "total": r"(?:Total(?!\s*Tax))[:\s]*([$€£]?\s*[0-9,.\-]+)",
            "grand_total": r"(?:Grand\s*Total)[:\s]*([$€£]?\s*[0-9,.\-]+)",
        }
        text = "\n".join(lines)

        m = re.search(patterns["invoice_number"], text, flags=re.IGNORECASE)
        if m:
            header["invoice_number"] = m.group(1).strip()

        m = re.search(patterns["invoice_date"], text, flags=re.IGNORECASE)
        if m:
            header["invoice_date"] = _parse_date(m.group(1))

        for key in ("subtotal", "tax", "total", "grand_total"):
            m = re.search(patterns[key], text, flags=re.IGNORECASE)
            if m:
                header[key] = _parse_money(m.group(1))

        # Line item heuristic: "desc ... qty <num> <unit> @ <unit_price> = <total>"
        line_regex = re.compile(
            r"^(?P<desc>.+?)\s+(?:qty|quantity)\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z]+)\s*@\s*\$?(?P<unit_price>\d+(?:\.\d+)?)\s*=\s*\$?(?P<total>\d+(?:\.\d+)?)$",
            flags=re.IGNORECASE,
        )
        for line in lines:
            m = line_regex.match(line)
            if not m:
                continue
            desc = m.group("desc").strip()
            qty = float(m.group("qty"))
            unit = _normalize_unit(m.group("unit"))
            unit_price = float(m.group("unit_price"))
            total = float(m.group("total"))
            items.append(
                {
                    "description": desc,
                    "quantity": qty,
                    "unit": unit,
                    "unit_price": unit_price,
                    "total_price": total,
                    "category": _infer_category(desc),
                    "normalized_unit": unit,
                    "normalized_quantity": qty,
                    "normalized_unit_price": unit_price,
                }
            )

        # Fallback: if no items parsed, try a simpler pattern "desc - $amount"
        if not items:
            simple_re = re.compile(r"^(?P<desc>.+?)\s*-\s*\$?(?P<total>\d+(?:\.\d+)?)$", flags=re.IGNORECASE)
            for line in lines:
                m = simple_re.match(line)
                if m:
                    desc = m.group("desc").strip()
                    total = float(m.group("total"))
                    items.append(
                        {
                            "description": desc,
                            "quantity": None,
                            "unit": None,
                            "unit_price": None,
                            "total_price": total,
                            "category": _infer_category(desc),
                            "normalized_unit": None,
                            "normalized_quantity": None,
                            "normalized_unit_price": None,
                        }
                    )

        # Post-normalization: flag high value items
        for it in items:
            total = it.get("total_price") or 0.0
            it["flagged_high_value"] = bool(total >= 500.0)

        return header, items
