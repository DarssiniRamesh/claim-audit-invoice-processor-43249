from src.services.normalization.normalizer import Normalizer


def test_detect_usd_by_symbol_and_parse_totals():
    raw = """
    ACME Restoration LLC
    Invoice #: INV-1001
    Invoice Date: 03/15/2025
    Subtotal: $1,200.50
    Tax: $99.50
    Grand Total: $1,300.00
    Labor - Technician - qty 10 hr @ $50.00 = $500.00
    Fans rental   3   day   25.00   75.00
    """
    header, items = Normalizer().parse_invoice(raw)
    assert header["currency"] == "USD"
    assert header["subtotal"] == 1200.50
    assert header["tax"] == 99.50
    assert header["grand_total"] == 1300.00
    assert len(items) >= 2
    # First item exact pattern
    it0 = items[0]
    assert it0["unit"] == "hour"
    assert it0["quantity"] == 10
    assert it0["unit_price"] == 50.00
    assert it0["total_price"] == 500.00
    assert it0["currency"] == "USD"
    assert 0.0 <= it0["confidence"] <= 1.0


def test_detect_eur_by_code_and_decimal_comma():
    raw = """
    Vendor GmbH
    Invoice Number: 2025-07-001
    Date: 15-03-2025
    Total EUR 1.234,56
    Items:
    Water extraction - qty 12 hrs @ €35,00 = €420,00
    Materials - Poly sheeting - €200,00
    """
    header, items = Normalizer().parse_invoice(raw)
    assert header["currency"] == "EUR"
    assert header["total"] is None or isinstance(header["total"], float)
    # First item must parse quantity, unit, and prices with comma decimals
    li = next((x for x in items if "Water extraction" in x["description"]), None)
    assert li is not None
    assert li["quantity"] == 12
    assert li["unit"] == "hour"
    assert abs(li["unit_price"] - 35.00) < 0.001
    assert abs(li["total_price"] - 420.00) < 0.001
    assert li["currency"] == "EUR"


def test_detect_gbp_by_symbol_and_parentheses_negative():
    raw = """
    Best Services Ltd
    Invoice Date: 2025-03-15
    Subtotal: £1,234.56
    Tax: (1,200.00)
    Total: £34.56
    Line - qty 2 hr @ £17.28 = £34.56
    """
    header, items = Normalizer().parse_invoice(raw)
    assert header["currency"] == "GBP"
    assert abs(header["subtotal"] - 1234.56) < 0.001
    # Negative parentheses-tax
    assert header["tax"] == -1200.00
    assert items[0]["currency"] == "GBP"


def test_columnar_table_parsing_and_inferred_unit_price():
    raw = """
    Reliable Restorations
    Description        Qty     Unit     Rate     Amount
    Drywall Removal    12      hr       35.00    420.00
    Equipment Rental   3       day                75.00
    """
    header, items = Normalizer().parse_invoice(raw)
    # Drywall row parsed
    li1 = next((x for x in items if "Drywall Removal" in x["description"]), None)
    assert li1 is not None
    assert li1["quantity"] == 12
    assert li1["unit"] == "hour"
    assert abs((li1["unit_price"] or 0) - 35.00) < 0.001
    assert abs((li1["total_price"] or 0) - 420.00) < 0.001
    # Equipment row inferred unit_price from qty/total
    li2 = next((x for x in items if "Equipment Rental" in x["description"]), None)
    assert li2 is not None
    assert li2["quantity"] == 3
    assert li2["unit"] == "day"
    assert abs((li2["total_price"] or 0) - 75.00) < 0.001
    assert abs((li2["unit_price"] or 0) - 25.00) < 0.001
    assert 0.0 <= li2["confidence"] <= 1.0


def test_line_level_currency_overrides_header():
    raw = """
    Mixed Currency Vendor
    Grand Total: $1,000.00
    Special EU Service - qty 2 hr @ €50,00 = €100,00
    """
    header, items = Normalizer().parse_invoice(raw)
    assert header["currency"] == "USD"
    euro_line = next((x for x in items if "Special EU Service" in x["description"]), None)
    assert euro_line is not None
    assert euro_line["currency"] == "EUR"
    assert abs(euro_line["unit_price"] - 50.00) < 0.001
    assert abs(euro_line["total_price"] - 100.00) < 0.001
