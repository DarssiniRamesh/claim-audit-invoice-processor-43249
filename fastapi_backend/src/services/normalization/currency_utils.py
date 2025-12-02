from __future__ import annotations

import re
from typing import Optional, Tuple

# PUBLIC_INTERFACE
def symbol_to_code(symbol: str) -> Optional[str]:
    """Map a currency symbol or prefixed symbol (e.g., US$) to an ISO 4217 currency code.

    Returns:
        The ISO currency code (e.g., 'USD') or None if unknown.
    """
    s = symbol.strip().upper()
    # Normalize common prefixed symbol formats
    # e.g., US$, CA$, A$
    if s.endswith("$") and len(s) > 1:
        prefix = s[:-1]
        if prefix in {"US", "USD"}:
            return "USD"
        if prefix in {"CA", "CAD"}:
            return "CAD"
        if prefix in {"AU", "AUD", "A"}:
            return "AUD"

    # Single symbol map
    symbol_map = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
        "￥": "JPY",
        "₹": "INR",
        "₣": "CHF",
        "₽": "RUB",
        "₩": "KRW",
        "R$": "BRL",
        "C$": "CAD",
        "CA$": "CAD",
        "A$": "AUD",
        "AU$": "AUD",
        "HK$": "HKD",
        "S$": "SGD",
        "NZ$": "NZD",
    }
    return symbol_map.get(symbol) or symbol_map.get(s)


# PUBLIC_INTERFACE
def normalize_currency_symbol_or_code(token: str) -> Optional[str]:
    """Normalize a token that may be a currency symbol or code to an ISO 4217 code.

    Handles symbols like $, €, £ and codes like USD, EUR, GBP (case-insensitive).
    """
    if not token:
        return None
    t = token.strip()
    # Attempt direct symbol mapping
    code = symbol_to_code(t)
    if code:
        return code

    # Attempt code mapping
    t_up = t.upper()
    known = {
        "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR", "CHF", "CNY", "CNH", "HKD",
        "SGD", "NZD", "BRL", "MXN", "ZAR", "SEK", "NOK", "DKK", "PLN", "TRY", "RUB",
        "TWD", "THB", "IDR", "VND", "KRW",
    }
    if t_up in known:
        return t_up
    return None


_CURRENCY_CODE_RE = re.compile(
    r"\b(?P<code>USD|EUR|GBP|CAD|AUD|JPY|INR|CHF|CNY|CNH|HKD|SGD|NZD|BRL|MXN|ZAR|SEK|NOK|DKK|PLN|TRY|RUB|TWD|THB|IDR|VND|KRW)\b",
    flags=re.IGNORECASE,
)


# PUBLIC_INTERFACE
def detect_currency_in_text(text: str) -> Tuple[Optional[str], float, str]:
    """Detect a currency code from text using symbols and codes with simple heuristics.

    Returns:
        (currency_code, confidence, method)
        - currency_code: ISO code (e.g., 'USD') or None if not detected
        - confidence: float 0..1
        - method: 'symbol', 'code', or 'unknown'
    """
    if not text:
        return None, 0.0, "unknown"

    # Prefer detecting explicit codes first near totals
    m = _CURRENCY_CODE_RE.search(text)
    if m:
        code = m.group("code").upper()
        return code, 0.95, "code"

    # Detect symbols
    # Search for the common currency symbols; if multiple found, choose the first from priorities
    priorities = [
        ("USD", [r"\bUS\$\b", r"\$"]),
        ("EUR", [r"€"]),
        ("GBP", [r"£"]),
        ("CAD", [r"\bCA\$\b", r"\bC\$\b"]),
        ("AUD", [r"\bAU\$\b", r"\bA\$\b"]),
        ("JPY", [r"¥", r"￥"]),
        ("INR", [r"₹"]),
        ("HKD", [r"HK\$"]),
        ("SGD", [r"S\$"]),
        ("NZD", [r"NZ\$"]),
        ("BRL", [r"R\$"]),
        ("RUB", [r"₽"]),
    ]
    for code, patterns in priorities:
        for pat in patterns:
            if re.search(pat, text):
                return code, 0.9, "symbol"

    return None, 0.0, "unknown"
