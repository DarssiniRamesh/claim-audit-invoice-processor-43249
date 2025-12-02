from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.services.normalization.currency_utils import (
    detect_currency_in_text,
    normalize_currency_symbol_or_code,
)

logger = logging.getLogger("app.normalization")


_UNIT_MAP = {
    "hr": "hour",
    "hrs": "hour",
    "hour": "hour",
    "hours": "hour",
    "sqft": "square_foot",
    "ft2": "square_foot",
    "sf": "square_foot",
    "lf": "linear_foot",
    "ft": "linear_foot",
    "ea": "each",
    "each": "each",
    "unit": "each",
    "unit(s)": "each",
    "day": "day",
    "days": "day",
    "yd3": "cubic_yard",
    "cuyd": "cubic_yard",
}

_CATEGORY_KEYWORDS = {
    "labor": ["labor", "technician", "crew", "hour", "hr", "hrs"],
    "materials": ["material", "sheetrock", "drywall", "lumber", "paint", "sealant", "poly", "sheeting"],
    "equipment": ["equipment", "dehumidifier", "air mover", "pump", "fan", "blower"],
    "disposal": ["haul", "disposal", "dump", "debris"],
    "mold_remediation": ["mold", "remediation"],
    "water_mitigation": ["water", "mitigation", "extraction", "drying", "dehumidification"],
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


def _strip_nbsp(s: str) -> str:
    """Remove common non-breaking space characters and invisible separators."""
    return s.replace("\u00A0", " ").replace("\u2007", " ").replace("\u202F", " ").replace("\ufeff", "")


def _clean_money_string(val: str) -> Tuple[str, bool]:
    """Basic cleanup: handle parentheses for negatives, normalize spaces and remove trailing/leading text."""
    s = _strip_nbsp(val or "").strip()
    negative = False
    if "(" in s and ")" in s:
        negative = True
        s = s.replace("(", "").replace(")", "")
    # Replace common OCR artifacts (e.g., spaces inside numbers like '1 234,56')
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    return s.strip(), negative


def _detect_decimal_separator(s: str) -> Optional[str]:
    """Heuristic to detect decimal separator in a numeric string that may include , . or both."""
    last_dot = s.rfind(".")
    last_comma = s.rfind(",")
    if last_dot == -1 and last_comma == -1:
        return None
    if last_dot != -1 and last_comma != -1:
        # Use the rightmost separator as decimal sep
        return "." if last_dot > last_comma else ","
    sep = "." if last_dot != -1 else ","
    # If exactly two digits after separator at the end -> decimal
    m = re.search(rf"\{sep}\d{{1,2}}\s*$", s)
    if m:
        return sep
    # If 3 digits and then end or another sep, likely thousands
    return None


def _normalize_numeric_string(s: str) -> str:
    """Remove any characters except digits and separators . , - and spaces and apostrophes."""
    s = re.sub(r"[^0-9,\.\-\s']", "", s)
    return s


def _to_float_from_separators(s: str, decimal_sep: Optional[str], negative_flag: bool) -> Optional[float]:
    """Convert a string with potential thousand/decimal separators to float."""
    if not s:
        return None
    # Remove apostrophes often used as thousands (e.g., 1'234.56)
    s = s.replace("'", "")
    # Remove spaces
    s = s.replace(" ", "")

    if decimal_sep == ",":
        # Decimal is comma; dots are thousands
        s = s.replace(".", "")
        s = s.replace(",", ".")
    elif decimal_sep == ".":
        # Decimal is dot; commas are thousands
        s = s.replace(",", "")
    else:
        # No clear decimal separator; remove commas and dots as thousands
        # Keep the last separator as decimal if possible (e.g., 1,234.56 -> 1234.56)
        last_dot = s.rfind(".")
        last_comma = s.rfind(",")
        if last_dot > last_comma and last_dot != -1:
            # dot as decimal
            s = s.replace(",", "")
        elif last_comma > last_dot and last_comma != -1:
            # comma as decimal
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "").replace(".", "")

    try:
        val = float(s)
        if negative_flag:
            val = -val
        return val
    except Exception:
        return None


def _parse_money(val: str) -> Optional[float]:
    """Locale-aware monetary parser.

    Handles:
    - Thousands separators (comma, dot, space, apostrophe)
    - Decimal separators (comma, dot)
    - Parentheses for negatives
    - Mixed OCR spacing artifacts
    """
    if val is None:
        return None
    s, negative_by_paren = _clean_money_string(val)
    # Remove currency codes/symbols around edges, but keep separators/numbers
    s = re.sub(r"(USD|EUR|GBP|CAD|AUD|JPY|INR|CHF|CNY|CNH|HKD|SGD|NZD|BRL|MXN|ZAR|SEK|NOK|DKK|PLN|TRY|RUB|KRW|TWD|THB|IDR|VND)\b", "", s, flags=re.IGNORECASE)
    s = s.replace("$", "").replace("€", "").replace("£", "").replace("¥", "").replace("₹", "").replace("￥", "")
    s = s.replace("R$", "").replace("C$", "").replace("CA$", "").replace("A$", "").replace("AU$", "").replace("HK$", "").replace("S$", "").replace("NZ$", "")
    s = s.strip()

    s = _normalize_numeric_string(s)
    if not s or s in {".", ",", "-", "''"}:
        return None

    decimal_sep = _detect_decimal_separator(s)
    return _to_float_from_separators(s, decimal_sep, negative_by_paren)


def _parse_date(val: str) -> Optional[str]:
    # Attempt common formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(val.strip(), fmt)
            return dt.date().isoformat()
        except Exception:
            continue
    return None


def _is_header_row(line: str) -> bool:
    l = line.lower()
    return all(term in l for term in ["desc", "qty"]) or all(
        term in l for term in ["description", "quantity"]
    )


def _split_columns(line: str) -> List[str]:
    # Split by multiple spaces or tabs while preserving single spaces inside tokens
    return [tok.strip() for tok in re.split(r"\s{2,}|\t+", line) if tok.strip()]


def _extract_numbers_with_context(tokens: List[str]) -> List[Tuple[int, str, Optional[float], Optional[str]]]:
    """Return list of (index, token, parsed_float, detected_currency) for numeric or money-like tokens."""
    out: List[Tuple[int, str, Optional[float], Optional[str]]] = []
    for idx, tok in enumerate(tokens):
        cur_code = normalize_currency_symbol_or_code(tok) or normalize_currency_symbol_or_code(re.sub(r"[0-9\.\,\s]", "", tok))
        # Parse money or numeric
        # Keep numeric even if integer; quantities often integers
        # Distinguish purely numeric vs money-like by presence of separators/decimals
        num = None
        if re.search(r"\d", tok):
            num = _parse_money(tok)
        out.append((idx, tok, num, cur_code))
    return out


def _infer_unit_from_tokens(tokens: List[str]) -> Optional[str]:
    # Look for known units in tokens
    for tok in tokens:
        u = _normalize_unit(tok)
        if u in _UNIT_MAP.values():
            return u
    # Look for hints
    joined = " ".join(tokens).lower()
    for key in ["hour", "day", "each", "linear_foot", "square_foot", "cubic_yard"]:
        if key in joined:
            return key
    return None


def _parse_line_item_from_tokens(line: str, default_currency: Optional[str]) -> Optional[Dict[str, Any]]:
    """Attempt to parse a line item from a line of text using multiple heuristics.

    Returns a dict with keys: description, quantity, unit, unit_price, total_price, currency, category, normalized_*
    or None if the line doesn't look like a line item.
    """
    line = _strip_nbsp(line)
    if not line or _is_header_row(line):
        return None

    # 1) Pattern with explicit markers: qty, unit @ price = total
    explicit = re.compile(
        r"^(?P<desc>.+?)\s+(?:qty|quantity)\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z]+)"
        r"(?:\s*@\s*(?P<price_sym>[$€£])?\s*(?P<unit_price>[\d\.,\s'()-]+))?"
        r"(?:\s*=\s*(?P<total_sym>[$€£])?\s*(?P<total>[\d\.,\s'()-]+))?$",
        flags=re.IGNORECASE,
    )
    m = explicit.match(line)
    if m:
        desc = m.group("desc").strip()
        qty = _parse_money(m.group("qty"))  # safe because it may be int/float
        unit = _normalize_unit(m.group("unit"))
        unit_price = _parse_money(m.group("unit_price")) if m.group("unit_price") else None
        total = _parse_money(m.group("total")) if m.group("total") else None

        cur = None
        if m.group("total_sym"):
            cur = normalize_currency_symbol_or_code(m.group("total_sym"))
        if not cur and m.group("price_sym"):
            cur = normalize_currency_symbol_or_code(m.group("price_sym"))
        if not cur:
            cur = default_currency

        inferred = False
        if unit_price is None and total is not None and qty:
            unit_price = round(total / qty, 4)
            inferred = True
            logger.warning("Inferred unit_price from total/qty for line: %s", line)

        if total is None and qty is not None and unit_price is not None:
            total = round(qty * unit_price, 2)
            inferred = True
            logger.warning("Inferred total from qty*unit_price for line: %s", line)

        confidence = 0.9
        if inferred:
            confidence = 0.75

        return {
            "description": desc,
            "quantity": qty,
            "unit": unit,
            "unit_price": unit_price,
            "total_price": total,
            "currency": cur,
            "category": _infer_category(desc),
            "normalized_unit": unit,
            "normalized_quantity": qty,
            "normalized_unit_price": unit_price,
            "confidence": confidence,
        }

    # 2) Column-aligned pattern: desc  qty  unit  unit_price  total
    tokens = _split_columns(line)
    if len(tokens) >= 3:
        # Heuristics: first token often description (or first 1..n tokens); last token often total
        # Identify numeric tokens and currencies
        num_info = _extract_numbers_with_context(tokens)
        numeric_positions = [(i, t, n, c) for (i, t, n, c) in num_info if n is not None]
        qty_candidates = [(i, t, n, c) for (i, t, n, c) in numeric_positions if i > 0]  # skip first column usually desc

        qty = None
        unit_price = None
        total = None
        cur = None
        unit = _infer_unit_from_tokens(tokens)

        # Try to assign total as the rightmost numeric
        if numeric_positions:
            i_total, t_total, n_total, c_total = numeric_positions[-1]
            total = n_total
            if c_total:
                cur = c_total

        # Try to assign unit_price as the second rightmost numeric with decimal
        for i, t, n, c in reversed(numeric_positions[:-1]):
            unit_price = n
            if c and not cur:
                cur = c
            break

        # Quantity: a numeric token before price columns with no decimal or small magnitude
        for i, t, n, c in qty_candidates:
            if i < (numeric_positions[-1][0]) and n is not None:
                # prefer integers or one decimal place
                if re.match(r"^\d+(\.0)?$", str(n)) or n <= 10000:
                    qty = n
                    break

        # Description: join tokens up to first numeric token
        first_numeric_idx = numeric_positions[0][0] if numeric_positions else 1
        desc = " ".join(tokens[:first_numeric_idx]).strip()
        if not desc:
            desc = tokens[0]

        if not cur:
            cur = default_currency

        inferred = False
        if unit_price is None and total is not None and qty:
            unit_price = round(total / qty, 4)
            inferred = True
            logger.warning("Inferred unit_price from total/qty (columns) for line: %s", line)

        if total is None and qty is not None and unit_price is not None:
            total = round(qty * unit_price, 2)
            inferred = True
            logger.warning("Inferred total from qty*unit_price (columns) for line: %s", line)

        # Validate that at least desc and a total are present
        if desc and (total is not None or unit_price is not None):
            confidence = 0.85
            if inferred:
                confidence = 0.7
            return {
                "description": desc,
                "quantity": qty,
                "unit": unit,
                "unit_price": unit_price,
                "total_price": total,
                "currency": cur,
                "category": _infer_category(desc),
                "normalized_unit": unit,
                "normalized_quantity": qty,
                "normalized_unit_price": unit_price,
                "confidence": confidence,
            }

    # 3) Fallback: "desc - $amount" or "desc amount"
    simple_re = re.compile(r"^(?P<desc>.+?)\s*(?:-|:)?\s*(?P<cur>(?:[A-Za-z]{3}|[$€£]))?\s*(?P<total>[\d\.,\s'()-]+)$", flags=re.IGNORECASE)
    m = simple_re.match(line)
    if m:
        desc = m.group("desc").strip()
        total = _parse_money(m.group("total"))
        cur = None
        tok_cur = m.group("cur")
        if tok_cur:
            cur = normalize_currency_symbol_or_code(tok_cur)
        if not cur:
            cur = default_currency
        return {
            "description": desc,
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "total_price": total,
            "currency": cur,
            "category": _infer_category(desc),
            "normalized_unit": None,
            "normalized_quantity": None,
            "normalized_unit_price": None,
            "confidence": 0.6 if total is not None else 0.4,
        }

    return None


class Normalizer:
    """Parses raw text into an invoice header and line items with normalized values."""

    # PUBLIC_INTERFACE
    def parse_invoice(self, raw_text: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Return (header, items) parsed from raw text.

        Parsing behavior:
        - Detect invoice-level currency from symbols or codes in the document (preferring occurrences near totals).
        - Parse numeric amounts (subtotal, tax, total, grand total) with locale-aware rules.
        - Extract line items using multiple heuristics:
            1) Explicit "qty/quantity <num> <unit> @ <unit_price> = <total>"
            2) Column-aligned tokens (split by multiple spaces/tabs): desc | qty | unit | unit_price | total
            3) Fallback "desc - amount"
        - Infer missing unit_price/total when possible; add confidence scoring and log warnings when inferred.

        Returns:
            header: Dict with keys vendor_name, invoice_number, invoice_date, currency, subtotal, tax, total, grand_total
            items: List of dicts representing line items. Each item includes currency and confidence fields.
        """
        header: Dict[str, Any] = {
            "vendor_name": None,
            "invoice_number": None,
            "invoice_date": None,
            "currency": None,
            "subtotal": None,
            "tax": None,
            "total": None,
            "grand_total": None,
        }
        items: List[Dict[str, Any]] = []

        lines = [line.strip() for line in (raw_text or "").splitlines() if line.strip()]
        if lines:
            header["vendor_name"] = lines[0][:255]

        text = "\n".join(lines)

        # Currency detection: prefer near totals if present, else document-wide heuristic
        totals_region = []
        for l in lines:
            if re.search(r"grand\s*total|total(?!\s*tax)|subtotal|tax", l, flags=re.IGNORECASE):
                totals_region.append(l)
        near_totals_text = "\n".join(totals_region) if totals_region else text

        cur_detected, cur_conf, method = detect_currency_in_text(near_totals_text)
        if cur_detected:
            header["currency"] = cur_detected
            logger.info("Detected currency=%s (method=%s, conf=%.2f)", cur_detected, method, cur_conf)
        else:
            # default to USD when unknown, with low confidence
            header["currency"] = "USD"
            logger.warning("Currency not detected; defaulting to USD (low confidence).")

        # Extract common fields
        patterns = {
            "invoice_number": r"(?:Invoice\s*(?:No\.|#|Number)[:\s]*)([A-Za-z0-9\-/]+)",
            "invoice_date": r"(?:Invoice\s*Date|Date)[:\s]*([0-9/\-]{6,10})",
            "subtotal": r"(?:Subtotal)[:\s]*(?:(?P<sub_cur>[A-Za-z]{3}|[$€£])\s*)?(?P<sub_amt>[\d\.,\s'()-]+)",
            "tax": r"(?:Tax)[:\s]*(?:(?P<tax_cur>[A-Za-z]{3}|[$€£])\s*)?(?P<tax_amt>[\d\.,\s'()-]+)",
            "total": r"(?:Total(?!\s*Tax))[:\s]*(?:(?P<tot_cur>[A-Za-z]{3}|[$€£])\s*)?(?P<tot_amt>[\d\.,\s'()-]+)",
            "grand_total": r"(?:Grand\s*Total)[:\s]*(?:(?P<grand_cur>[A-Za-z]{3}|[$€£])\s*)?(?P<grand_amt>[\d\.,\s'()-]+)",
        }

        m = re.search(patterns["invoice_number"], text, flags=re.IGNORECASE)
        if m:
            header["invoice_number"] = m.group(1).strip()

        m = re.search(patterns["invoice_date"], text, flags=re.IGNORECASE)
        if m:
            header["invoice_date"] = _parse_date(m.group(1))

        # Monetary fields with possible per-field currency
        for key, cur_group, amt_group in [
            ("subtotal", "sub_cur", "sub_amt"),
            ("tax", "tax_cur", "tax_amt"),
            ("total", "tot_cur", "tot_amt"),
            ("grand_total", "grand_cur", "grand_amt"),
        ]:
            m = re.search(patterns[key], text, flags=re.IGNORECASE)
            if m:
                amt_raw = m.group(amt_group)
                header[key] = _parse_money(amt_raw)
                cur_tok = m.group(cur_group)
                cur_for_field = normalize_currency_symbol_or_code(cur_tok) if cur_tok else None
                if cur_for_field and not header.get("currency"):
                    header["currency"] = cur_for_field
                elif cur_for_field and header.get("currency") != cur_for_field:
                    logger.warning(
                        "Field %s shows currency %s different from header currency %s",
                        key, cur_for_field, header.get("currency"),
                    )

        # Line item extraction
        for line in lines:
            it = _parse_line_item_from_tokens(line, header.get("currency"))
            if it:
                # Ensure currency per line; detect from line if possible
                cur_line, cur_conf_line, _method = detect_currency_in_text(line)
                if cur_line:
                    it["currency"] = cur_line
                elif not it.get("currency"):
                    it["currency"] = header.get("currency")

                # Post-normalization: flag high value items
                total = it.get("total_price") or 0.0
                it["flagged_high_value"] = bool((total or 0.0) >= 500.0)

                items.append(it)

        # If no items parsed, try a final very simple money bullet parser
        if not items:
            simple = re.compile(r"^(?P<desc>.+?)\s+(?P<cur>[A-Za-z]{3}|[$€£])?\s*(?P<total>[\d\.,\s'()-]+)$")
            for line in lines:
                m = simple.match(line)
                if m:
                    desc = m.group("desc").strip()
                    total = _parse_money(m.group("total"))
                    cur_line = normalize_currency_symbol_or_code(m.group("cur")) if m.group("cur") else header.get("currency")
                    items.append(
                        {
                            "description": desc,
                            "quantity": None,
                            "unit": None,
                            "unit_price": None,
                            "total_price": total,
                            "currency": cur_line,
                            "category": _infer_category(desc),
                            "normalized_unit": None,
                            "normalized_quantity": None,
                            "normalized_unit_price": None,
                            "confidence": 0.55 if total is not None else 0.4,
                            "flagged_high_value": bool((total or 0.0) >= 500.0) if total is not None else False,
                        }
                    )

        return header, items
