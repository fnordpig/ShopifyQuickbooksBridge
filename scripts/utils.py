#!/usr/bin/env python3
"""Shared utilities for shopify-qbo scripts."""

import re
from decimal import Decimal, ROUND_HALF_UP


def parse_private_note(note: str | None) -> list[dict]:
    """Parse PrivateNote into structured action entries.

    E.g., '[shopify-sync:gid://shopify/Customer/1001] Imported on 2026-03-14'
    Returns list of {"tag": "shopify-sync", "value": "gid://...", "detail": "Imported on 2026-03-14"}
    Also parses [shopify-qbo:fix], [shopify-qbo:delete], [shopify-qbo:undo] etc.
    """
    if not note:
        return []

    entries = []
    for match in re.finditer(r'\[([a-z-]+):([^\]]+)\]\s*(.*?)(?=\[|$)', note, re.DOTALL):
        entries.append({
            "tag": match.group(1),
            "value": match.group(2),
            "detail": match.group(3).strip(),
        })
    return entries


def normalize_shopify_customer(customer: dict) -> dict:
    """Normalize Shopify customer to comparable fields dict."""
    first = customer.get("firstName", "") or ""
    last = customer.get("lastName", "") or ""
    name = f"{first} {last}".strip()

    addr = customer.get("defaultAddress") or {}
    if not addr:
        addresses = customer.get("addresses", [])
        addr = addresses[0] if addresses else {}

    tags = customer.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return {
        "name": name,
        "email": customer.get("email", "") or "",
        "phone": customer.get("phone", "") or "",
        "address_line1": addr.get("address1", "") or "",
        "address_line2": addr.get("address2", "") or "",
        "city": addr.get("city", "") or "",
        "state": addr.get("provinceCode") or addr.get("province", "") or "",
        "zip": addr.get("zip", "") or "",
        "country": addr.get("countryCodeV2") or addr.get("country", "") or "",
        "tax_exempt": bool(customer.get("taxExempt", False)),
        "tags": tags,
        "shopify_id": customer.get("id", "") or "",
    }


def normalize_qbo_customer(customer: dict) -> dict:
    """Normalize QBO customer to comparable fields dict."""
    addr = customer.get("BillAddr", {}) or {}
    email = (customer.get("PrimaryEmailAddr") or {}).get("Address", "")
    phone = (customer.get("PrimaryPhone") or {}).get("FreeFormNumber", "")

    # Extract shopify_id from PrivateNote or Notes
    shopify_id = ""
    private_note = customer.get("PrivateNote", "")
    entries = parse_private_note(private_note)
    for entry in entries:
        if entry["tag"] == "shopify-sync" and "shopify" in entry["value"]:
            shopify_id = entry["value"]
            break

    # Try Notes field as fallback
    if not shopify_id:
        notes = customer.get("Notes", "")
        id_match = re.search(r'Shopify ID:\s*(\S+)', notes)
        if id_match:
            shopify_id = id_match.group(1)

    # Extract tags from Notes
    tags = []
    notes = customer.get("Notes", "")
    tags_match = re.search(r'Shopify tags:\s*(.+?)(?:\s*\||$)', notes)
    if tags_match:
        tags = [t.strip() for t in tags_match.group(1).split(",") if t.strip()]

    return {
        "name": customer.get("DisplayName", "") or "",
        "email": email,
        "phone": phone,
        "address_line1": addr.get("Line1", "") or "",
        "address_line2": addr.get("Line2", "") or "",
        "city": addr.get("City", "") or "",
        "state": addr.get("CountrySubDivisionCode", "") or "",
        "zip": addr.get("PostalCode", "") or "",
        "country": addr.get("Country", "") or "",
        "tax_exempt": not customer.get("Taxable", True),
        "tags": tags,
        "shopify_id": shopify_id,
    }


def normalize_shopify_order(order: dict) -> dict:
    """Normalize Shopify order to comparable fields."""
    customer = order.get("customer") or {}
    line_items = order.get("lineItems", [])
    # Handle edges/nodes format
    items = []
    for item in line_items:
        if "node" in item:
            item = item["node"]
        items.append({
            "title": item.get("title", ""),
            "quantity": int(item.get("quantity", 1)),
            "unit_price": str(item.get("originalUnitPrice") or item.get("price", "0")),
        })

    shipping_total = Decimal("0")
    for s in order.get("shippingLines", []):
        if "node" in s:
            s = s["node"]
        shipping_total += Decimal(str(s.get("price", "0")))

    tax_lines = order.get("taxLines", [])
    tax_rate = ""
    if tax_lines:
        tax_rate = str(tax_lines[0].get("rate", ""))

    return {
        "order_name": order.get("name", ""),
        "date": (order.get("createdAt", "") or "")[:10],
        "customer_email": customer.get("email", "") or "",
        "customer_name": f"{customer.get('firstName', '') or ''} {customer.get('lastName', '') or ''}".strip(),
        "subtotal": str(order.get("subtotalPrice") or order.get("subtotalPriceSet", {}).get("shopMoney", {}).get("amount", "0")),
        "tax_total": str(order.get("totalTax") or order.get("totalTaxSet", {}).get("shopMoney", {}).get("amount", "0")),
        "tax_rate": tax_rate,
        "shipping_total": str(shipping_total),
        "discount_total": str(order.get("totalDiscounts") or order.get("totalDiscountsSet", {}).get("shopMoney", {}).get("amount", "0")),
        "grand_total": str(order.get("totalPrice") or order.get("totalPriceSet", {}).get("shopMoney", {}).get("amount", "0")),
        "line_item_count": len(items),
        "items": items,
    }


def normalize_qbo_invoice(invoice: dict) -> dict:
    """Normalize QBO invoice to comparable fields."""
    lines = invoice.get("Line", [])
    sales_lines = [line for line in lines if line.get("DetailType") == "SalesItemLineDetail"]
    discount_lines = [line for line in lines if line.get("DetailType") == "DiscountLineDetail"]
    shipping_lines = [line for line in sales_lines if "Shipping" in (line.get("Description") or "")]
    product_lines = [line for line in sales_lines if "Shipping" not in (line.get("Description") or "")]

    subtotal = sum((Decimal(str(line["Amount"])) for line in product_lines), Decimal("0")).quantize(Decimal("0.01"))
    shipping = sum((Decimal(str(line["Amount"])) for line in shipping_lines), Decimal("0")).quantize(Decimal("0.01"))
    discount = sum((Decimal(str(line["Amount"])) for line in discount_lines), Decimal("0")).quantize(Decimal("0.01"))

    tax_detail = invoice.get("TxnTaxDetail", {}) or {}
    tax_total = Decimal(str(tax_detail.get("TotalTax", 0))).quantize(Decimal("0.01"))
    tax_lines = tax_detail.get("TaxLine", [])
    tax_rate = ""
    if tax_lines:
        tl_detail = tax_lines[0].get("TaxLineDetail", {})
        tax_rate = str(tl_detail.get("TaxPercent", ""))

    items = []
    for line in product_lines:
        detail = line.get("SalesItemLineDetail", {})
        items.append({
            "title": line.get("Description", ""),
            "quantity": int(detail.get("Qty", 1)),
            "unit_price": str(detail.get("UnitPrice", "0")),
        })

    grand_total = Decimal(str(invoice.get("TotalAmt", 0))).quantize(Decimal("0.01"))

    return {
        "doc_number": invoice.get("DocNumber", ""),
        "date": invoice.get("TxnDate", ""),
        "customer_email": invoice.get("_customer_email", ""),
        "customer_name": invoice.get("_customer_name", ""),
        "subtotal": str(subtotal),
        "tax_total": str(tax_total),
        "tax_rate": tax_rate,
        "shipping_total": str(shipping),
        "discount_total": str(discount),
        "grand_total": str(grand_total),
        "line_item_count": len(product_lines),
        "items": items,
    }


def compare_fields(a: dict, b: dict, fields: list[str] | None = None) -> list[dict]:
    """Compare two normalized dicts field by field.

    Returns list of {"field": "name", "a": "Jane", "b": "J.", "match": False}
    """
    if fields is None:
        fields = sorted(set(list(a.keys()) + list(b.keys())))

    results = []
    for field in fields:
        val_a = a.get(field, "")
        val_b = b.get(field, "")
        # Normalize for comparison
        str_a = str(val_a) if val_a is not None else ""
        str_b = str(val_b) if val_b is not None else ""
        results.append({
            "field": field,
            "a": str_a,
            "b": str_b,
            "match": str_a == str_b,
        })
    return results


def format_currency(amount) -> str:
    """Format as $X,XXX.XX"""
    d = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Format with thousands separator
    sign = "-" if d < 0 else ""
    integer_part = abs(int(d))
    decimal_part = abs(d) - abs(int(d))
    cents = str(decimal_part.quantize(Decimal("0.01")))[2:]  # strip "0."
    formatted_int = f"{integer_part:,}"
    return f"${sign}{formatted_int}.{cents}"
