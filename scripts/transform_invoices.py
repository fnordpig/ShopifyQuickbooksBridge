#!/usr/bin/env python3
"""
Transform Shopify orders to QuickBooks Online invoice format with tax mapping.

Usage:
    python transform_invoices.py --input shopify_orders.json --output qbo_invoices.json --tax-map tax-mapping.json

Input: JSON array of Shopify order objects (from Shopify MCP get-orders)
Output: JSON array of QBO-ready invoice objects
"""

import argparse
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def load_tax_mapping(path: str) -> dict:
    """Load tax mapping configuration."""
    with open(path, "r") as f:
        return json.load(f)


def resolve_tax_code(tax_title: str, tax_map: dict) -> str:
    """Resolve a Shopify tax title to a QBO tax code using the mapping config."""
    # Check all region mappings
    for region, mappings in tax_map.get("mappings", {}).items():
        if tax_title in mappings:
            return mappings[tax_title]

    # Try partial matching
    title_lower = tax_title.lower()
    for region, mappings in tax_map.get("mappings", {}).items():
        for key, value in mappings.items():
            if key.lower() in title_lower or title_lower in key.lower():
                return value

    # Fall back to defaults
    defaults = tax_map.get("defaults", {})
    if "exempt" in title_lower or "free" in title_lower or "0%" in title_lower:
        return defaults.get("exempt", "NON")

    return defaults.get("unknown", "TAX")


def parse_order_number(order_name: str) -> str:
    """Extract order number from Shopify order name (e.g., '#1001' → '1001')."""
    return re.sub(r"[^0-9]", "", str(order_name))


def to_decimal(value: Any) -> Decimal:
    """Safely convert a value to Decimal."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def transform_line_item(item: dict, tax_map: dict) -> dict:
    """Transform a Shopify line item to a QBO invoice line."""
    quantity = int(item.get("quantity", 1))
    unit_price = to_decimal(item.get("originalUnitPrice") or item.get("price", "0"))
    amount = (unit_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Determine tax code from line item's tax lines
    item_tax_lines = item.get("taxLines", [])
    tax_code = "NON"
    if item_tax_lines:
        # Use the first tax line's title to determine code
        first_tax = item_tax_lines[0]
        tax_code = resolve_tax_code(first_tax.get("title", ""), tax_map)

    line = {
        "DetailType": "SalesItemLineDetail",
        "Amount": float(amount),
        "Description": item.get("title", ""),
        "SalesItemLineDetail": {
            "ItemRef": {"value": "1", "name": "Sales"},
            "Qty": quantity,
            "UnitPrice": float(unit_price),
            "TaxCodeRef": {"value": tax_code},
        },
        "_shopify_variant_id": item.get("variantId", ""),
        "_shopify_sku": item.get("sku", ""),
    }

    return line


def transform_shipping_line(shipping: dict) -> dict:
    """Transform a Shopify shipping line to a QBO invoice line."""
    price = to_decimal(shipping.get("price", "0"))

    return {
        "DetailType": "SalesItemLineDetail",
        "Amount": float(price),
        "Description": f"Shipping: {shipping.get('title', 'Standard')}",
        "SalesItemLineDetail": {
            "ItemRef": {"value": "1", "name": "Shipping"},
            "Qty": 1,
            "UnitPrice": float(price),
            "TaxCodeRef": {"value": "NON"},
        },
    }


def transform_discount(total_discounts: Decimal) -> dict | None:
    """Create a QBO discount line if there are discounts."""
    if total_discounts <= 0:
        return None

    return {
        "DetailType": "DiscountLineDetail",
        "Amount": float(total_discounts),
        "DiscountLineDetail": {
            "PercentBased": False,
        },
    }


def transform_tax_detail(tax_lines: list, tax_map: dict) -> dict:
    """Transform Shopify order-level tax lines to QBO TxnTaxDetail."""
    total_tax = Decimal("0")
    qbo_tax_lines = []

    for tax_line in tax_lines:
        tax_amount = to_decimal(tax_line.get("price", "0"))
        tax_rate = to_decimal(tax_line.get("rate", "0"))
        tax_title = tax_line.get("title", "Tax")

        total_tax += tax_amount

        qbo_tax_line = {
            "Amount": float(tax_amount),
            "DetailType": "TaxLineDetail",
            "TaxLineDetail": {
                "TaxRateRef": {"value": resolve_tax_code(tax_title, tax_map)},
                "PercentBased": True,
                "TaxPercent": float((tax_rate * 100).quantize(Decimal("0.01"))),
                "NetAmountTaxable": 0,  # Will be calculated by QBO
            },
            "_shopify_tax_title": tax_title,
        }
        qbo_tax_lines.append(qbo_tax_line)

    return {
        "TotalTax": float(total_tax.quantize(Decimal("0.01"))),
        "TaxLine": qbo_tax_lines,
    }


def transform_order(order: dict, tax_map: dict) -> dict:
    """Transform a single Shopify order to QBO invoice format."""
    order_number = parse_order_number(order.get("name", ""))
    created_at = order.get("createdAt", "")
    txn_date = (
        created_at[:10]
        if created_at
        else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    # Customer reference (will be resolved by QBO MCP via email lookup)
    customer = order.get("customer", {}) or {}
    customer_email = customer.get("email", "")

    # Transform line items
    lines = []
    for item in order.get("lineItems", []):
        # Handle both edges/nodes format and flat array
        if "node" in item:
            item = item["node"]
        lines.append(transform_line_item(item, tax_map))

    # Shipping lines
    for shipping in order.get("shippingLines", []):
        if "node" in shipping:
            shipping = shipping["node"]
        lines.append(transform_shipping_line(shipping))

    # Discount
    total_discounts = to_decimal(
        order.get("totalDiscounts")
        or order.get("totalDiscountsSet", {}).get("shopMoney", {}).get("amount", "0")
    )
    discount_line = transform_discount(total_discounts)
    if discount_line:
        lines.append(discount_line)

    # Tax detail
    order_tax_lines = order.get("taxLines", [])
    tax_detail = transform_tax_detail(order_tax_lines, tax_map)

    # Build QBO invoice
    qbo_invoice: dict[str, Any] = {
        "DocNumber": f"SH-{order_number}",
        "TxnDate": txn_date,
        "Line": lines,
        "TxnTaxDetail": tax_detail,
        "PrivateNote": f"[shopify-sync:{order.get('id', '')}] Imported from Shopify order {order.get('name', '')} on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "_shopify_order_id": order.get("id", ""),
        "_shopify_order_name": order.get("name", ""),
        "_customer_email": customer_email,
        "_customer_name": f"{customer.get('firstName', '')} {customer.get('lastName', '')}".strip(),
        "_sync_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Customer ref placeholder (resolved during QBO load phase)
    if customer_email:
        qbo_invoice["_customer_lookup"] = {
            "strategy": "email",
            "value": customer_email,
        }

    # Financial summary for validation
    qbo_invoice["_validation"] = {
        "shopify_total_price": str(
            order.get("totalPrice")
            or order.get("totalPriceSet", {}).get("shopMoney", {}).get("amount", "0")
        ),
        "shopify_total_tax": str(
            order.get("totalTax")
            or order.get("totalTaxSet", {}).get("shopMoney", {}).get("amount", "0")
        ),
        "shopify_total_discounts": str(total_discounts),
        "shopify_subtotal": str(
            order.get("subtotalPrice")
            or order.get("subtotalPriceSet", {}).get("shopMoney", {}).get("amount", "0")
        ),
        "shopify_financial_status": order.get("financialStatus")
        or order.get("displayFinancialStatus", ""),
        "shopify_fulfillment_status": order.get("fulfillmentStatus")
        or order.get("displayFulfillmentStatus", ""),
    }

    return qbo_invoice


def main():
    parser = argparse.ArgumentParser(
        description="Transform Shopify orders to QBO invoices"
    )
    parser.add_argument(
        "--input", "-i", required=True, help="Path to Shopify orders JSON"
    )
    parser.add_argument(
        "--output", "-o", required=True, help="Path to write QBO invoices JSON"
    )
    parser.add_argument(
        "--tax-map", "-t", required=True, help="Path to tax-mapping.json"
    )
    parser.add_argument(
        "--status-filter",
        default="paid",
        help="Shopify financial status filter (default: paid)",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print output JSON"
    )
    args = parser.parse_args()

    # Load inputs
    with open(args.input, "r") as f:
        shopify_orders = json.load(f)

    tax_map = load_tax_mapping(args.tax_map)

    if not isinstance(shopify_orders, list):
        shopify_orders = [shopify_orders]

    # Filter by financial status if specified
    if args.status_filter != "all":
        original_count = len(shopify_orders)
        shopify_orders = [
            o
            for o in shopify_orders
            if (o.get("financialStatus") or o.get("displayFinancialStatus", "")).lower()
            == args.status_filter.lower()
            or args.status_filter == "all"
        ]
        filtered_count = original_count - len(shopify_orders)
    else:
        filtered_count = 0

    # Transform
    qbo_invoices = [transform_order(o, tax_map) for o in shopify_orders]

    # Aggregate tax summary
    total_tax = sum(
        Decimal(str(inv["TxnTaxDetail"]["TotalTax"])) for inv in qbo_invoices
    )
    total_revenue = sum(
        Decimal(str(line["Amount"]))
        for inv in qbo_invoices
        for line in inv["Line"]
        if line["DetailType"] == "SalesItemLineDetail"
    )

    # Stats
    stats = {
        "total_input": len(shopify_orders) + filtered_count,
        "filtered_out": filtered_count,
        "total_output": len(qbo_invoices),
        "total_line_items": sum(
            len(
                [
                    line
                    for line in inv["Line"]
                    if line["DetailType"] == "SalesItemLineDetail"
                ]
            )
            for inv in qbo_invoices
        ),
        "total_tax": float(total_tax),
        "total_revenue": float(total_revenue),
        "orders_with_discounts": sum(
            1
            for inv in qbo_invoices
            if any(line["DetailType"] == "DiscountLineDetail" for line in inv["Line"])
        ),
        "orders_missing_customer_email": sum(
            1 for inv in qbo_invoices if not inv.get("_customer_email")
        ),
    }

    # Output
    output = {
        "metadata": {
            "source": "shopify",
            "target": "quickbooks_online",
            "entity": "invoice",
            "transform_version": "1.0",
            "transformed_at": datetime.now(timezone.utc).isoformat(),
            "status_filter": args.status_filter,
            "stats": stats,
        },
        "invoices": qbo_invoices,
    }

    indent = 2 if args.pretty else None
    with open(args.output, "w") as f:
        json.dump(output, f, indent=indent, default=str)

    print(
        f"Transformed {stats['total_input']} Shopify orders → {stats['total_output']} QBO invoices"
    )
    print(f"  Filtered out: {stats['filtered_out']} (status ≠ {args.status_filter})")
    print(f"  Total line items: {stats['total_line_items']}")
    print(f"  Total tax: ${stats['total_tax']:.2f}")
    print(f"  Total revenue: ${stats['total_revenue']:.2f}")
    print(f"  Orders with discounts: {stats['orders_with_discounts']}")
    print(f"  Missing customer email: {stats['orders_missing_customer_email']}")
    print(f"Output written to: {args.output}")


if __name__ == "__main__":
    main()
