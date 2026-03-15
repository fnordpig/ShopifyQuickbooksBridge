#!/usr/bin/env python3
"""
Report generation for Shopify-QBO sync data.

Usage:
    python generate_report.py --type sync-status --shopify-orders orders.json --qbo-invoices invoices.json
    python generate_report.py --type reconciliation --shopify-orders orders.json --qbo-invoices invoices.json
    python generate_report.py --type tax --qbo-invoices invoices.json
    python generate_report.py --type financial --qbo-invoices invoices.json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from utils import format_currency, parse_private_note


def generate_sync_status_report(shopify_orders: list[dict], qbo_invoices: list[dict]) -> dict:
    """Generate sync status report: counts synced vs total."""
    # Build set of synced order numbers from QBO DocNumbers
    qbo_doc_numbers = set()
    for inv in qbo_invoices:
        doc = inv.get("DocNumber", "")
        if doc.startswith("SH-"):
            qbo_doc_numbers.add(doc)

    # Map Shopify orders to expected DocNumbers
    synced = 0
    unsynced_orders = []
    for order in shopify_orders:
        order_num = re.sub(r'[^0-9]', '', str(order.get("name", "")))
        doc_number = f"SH-{order_num}"
        if doc_number in qbo_doc_numbers:
            synced += 1
        else:
            unsynced_orders.append({
                "order_name": order.get("name", ""),
                "shopify_id": order.get("id", ""),
                "doc_number": doc_number,
            })

    sync_pct = (synced / len(shopify_orders) * 100) if shopify_orders else 0

    return {
        "report_type": "sync-status",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "total_shopify": len(shopify_orders),
            "total_qbo": len(qbo_invoices),
            "synced": synced,
            "unsynced": len(shopify_orders) - synced,
            "sync_percentage": round(sync_pct, 1),
            "unsynced_orders": unsynced_orders,
        },
    }


def generate_reconciliation_report(shopify_orders: list[dict], qbo_invoices: list[dict]) -> dict:
    """Generate reconciliation report: compare totals between systems."""
    # Shopify totals
    shopify_subtotal = Decimal("0")
    shopify_tax = Decimal("0")
    shopify_shipping = Decimal("0")
    shopify_discounts = Decimal("0")
    shopify_total = Decimal("0")

    for order in shopify_orders:
        shopify_subtotal += Decimal(str(order.get("subtotalPrice", "0") or "0"))
        shopify_tax += Decimal(str(order.get("totalTax", "0") or "0"))
        shopify_total += Decimal(str(order.get("totalPrice", "0") or "0"))
        shopify_discounts += Decimal(str(order.get("totalDiscounts", "0") or "0"))
        for s in order.get("shippingLines", []):
            if "node" in s:
                s = s["node"]
            shopify_shipping += Decimal(str(s.get("price", "0")))

    # QBO totals
    qbo_subtotal = Decimal("0")
    qbo_tax = Decimal("0")
    qbo_shipping = Decimal("0")
    qbo_discounts = Decimal("0")
    qbo_total = Decimal("0")

    for inv in qbo_invoices:
        qbo_total += Decimal(str(inv.get("TotalAmt", 0)))
        tax_detail = inv.get("TxnTaxDetail", {}) or {}
        qbo_tax += Decimal(str(tax_detail.get("TotalTax", 0)))
        for line in inv.get("Line", []):
            if line.get("DetailType") == "SalesItemLineDetail":
                amt = Decimal(str(line.get("Amount", 0)))
                desc = line.get("Description", "") or ""
                if "Shipping" in desc:
                    qbo_shipping += amt
                else:
                    qbo_subtotal += amt
            elif line.get("DetailType") == "DiscountLineDetail":
                qbo_discounts += Decimal(str(line.get("Amount", 0)))

    def q(d: Decimal) -> str:
        return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return {
        "report_type": "reconciliation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "shopify_order_count": len(shopify_orders),
            "qbo_invoice_count": len(qbo_invoices),
            "shopify_total_revenue": q(shopify_subtotal),
            "qbo_total_revenue": q(qbo_subtotal),
            "revenue_difference": q(shopify_subtotal - qbo_subtotal),
            "shopify_total_tax": q(shopify_tax),
            "qbo_total_tax": q(qbo_tax),
            "tax_difference": q(shopify_tax - qbo_tax),
            "shopify_total_shipping": q(shopify_shipping),
            "qbo_total_shipping": q(qbo_shipping),
            "shipping_difference": q(shopify_shipping - qbo_shipping),
            "shopify_total_discounts": q(shopify_discounts),
            "qbo_total_discounts": q(qbo_discounts),
            "discount_difference": q(shopify_discounts - qbo_discounts),
            "shopify_grand_total": q(shopify_total),
            "qbo_grand_total": q(qbo_total),
            "grand_total_difference": q(shopify_total - qbo_total),
        },
    }


def generate_tax_report(qbo_invoices: list[dict]) -> dict:
    """Generate tax report: group by tax code/jurisdiction."""
    tax_groups: dict[str, dict] = {}
    total_tax = Decimal("0")

    for inv in qbo_invoices:
        tax_detail = inv.get("TxnTaxDetail", {}) or {}
        for tax_line in tax_detail.get("TaxLine", []):
            tl_detail = tax_line.get("TaxLineDetail", {})
            tax_code = tl_detail.get("TaxRateRef", {}).get("value", "UNKNOWN")
            tax_pct = Decimal(str(tl_detail.get("TaxPercent", 0)))
            tax_amt = Decimal(str(tax_line.get("Amount", 0)))
            net_taxable = Decimal(str(tl_detail.get("NetAmountTaxable", 0)))
            shopify_title = tax_line.get("_shopify_tax_title", tax_code)

            total_tax += tax_amt

            key = f"{tax_code}_{tax_pct}"
            if key not in tax_groups:
                tax_groups[key] = {
                    "tax_code": tax_code,
                    "shopify_title": shopify_title,
                    "rate_percent": str(tax_pct),
                    "total_tax_collected": Decimal("0"),
                    "total_taxable_sales": Decimal("0"),
                    "invoice_count": 0,
                }
            tax_groups[key]["total_tax_collected"] += tax_amt
            tax_groups[key]["total_taxable_sales"] += net_taxable
            tax_groups[key]["invoice_count"] += 1

    def q(d: Decimal) -> str:
        return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    groups_list = []
    for g in tax_groups.values():
        groups_list.append({
            "tax_code": g["tax_code"],
            "shopify_title": g["shopify_title"],
            "rate_percent": g["rate_percent"],
            "total_tax_collected": q(g["total_tax_collected"]),
            "total_taxable_sales": q(g["total_taxable_sales"]),
            "invoice_count": g["invoice_count"],
        })

    return {
        "report_type": "tax",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "total_tax_collected": q(total_tax),
            "tax_group_count": len(groups_list),
            "tax_groups": groups_list,
        },
    }


def generate_financial_report(qbo_invoices: list[dict]) -> dict:
    """Generate financial summary report from QBO invoices."""
    total_revenue = Decimal("0")
    total_tax = Decimal("0")
    total_shipping = Decimal("0")
    total_discounts = Decimal("0")
    total_gross = Decimal("0")

    for inv in qbo_invoices:
        total_gross += Decimal(str(inv.get("TotalAmt", 0)))
        tax_detail = inv.get("TxnTaxDetail", {}) or {}
        total_tax += Decimal(str(tax_detail.get("TotalTax", 0)))
        for line in inv.get("Line", []):
            if line.get("DetailType") == "SalesItemLineDetail":
                amt = Decimal(str(line.get("Amount", 0)))
                desc = line.get("Description", "") or ""
                if "Shipping" in desc:
                    total_shipping += amt
                else:
                    total_revenue += amt
            elif line.get("DetailType") == "DiscountLineDetail":
                total_discounts += Decimal(str(line.get("Amount", 0)))

    def q(d: Decimal) -> str:
        return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    avg_order = (total_gross / len(qbo_invoices)) if qbo_invoices else Decimal("0")

    return {
        "report_type": "financial",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "invoice_count": len(qbo_invoices),
            "total_revenue": q(total_revenue),
            "total_tax": q(total_tax),
            "total_shipping": q(total_shipping),
            "total_discounts": q(total_discounts),
            "gross_total": q(total_gross),
            "net_revenue": q(total_revenue - total_discounts),
            "average_order_value": q(avg_order),
            "total_revenue_formatted": format_currency(total_revenue),
            "gross_total_formatted": format_currency(total_gross),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Generate reports from sync data")
    parser.add_argument("--type", required=True,
                        choices=["sync-status", "reconciliation", "tax", "financial"],
                        help="Report type")
    parser.add_argument("--shopify-orders", default=None, help="Path to Shopify orders JSON")
    parser.add_argument("--qbo-invoices", default=None, help="Path to QBO invoices JSON")
    parser.add_argument("--output", "-o", default=None, help="Output file (default: stdout)")
    parser.add_argument("--html-output", default=None, help="Path to write HTML dashboard")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")
    args = parser.parse_args()

    shopify_orders = []
    if args.shopify_orders:
        with open(args.shopify_orders, "r") as f:
            shopify_orders = json.load(f)
        if not isinstance(shopify_orders, list):
            shopify_orders = [shopify_orders]

    qbo_invoices = []
    if args.qbo_invoices:
        with open(args.qbo_invoices, "r") as f:
            qbo_invoices = json.load(f)
        if not isinstance(qbo_invoices, list):
            qbo_invoices = [qbo_invoices]

    if args.type == "sync-status":
        result = generate_sync_status_report(shopify_orders, qbo_invoices)
    elif args.type == "reconciliation":
        result = generate_reconciliation_report(shopify_orders, qbo_invoices)
    elif args.type == "tax":
        result = generate_tax_report(qbo_invoices)
    elif args.type == "financial":
        result = generate_financial_report(qbo_invoices)
    else:
        print(f"Unknown report type: {args.type}", file=sys.stderr)
        sys.exit(1)

    indent = 2 if args.pretty else None
    output_json = json.dumps(result, indent=indent, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        print(f"Output written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)

    if args.html_output:
        _write_html_report(result, args.html_output)
        print(f"HTML output written to: {args.html_output}", file=sys.stderr)


def _write_html_report(report: dict, path: str):
    """Write a simple HTML dashboard from a report dict."""
    title = report.get("report_type", "Report").replace("-", " ").title()
    data = report.get("data", {})

    rows = ""
    for key, value in data.items():
        if isinstance(value, (list, dict)):
            continue
        label = key.replace("_", " ").title()
        rows += f"<tr><td>{label}</td><td>{value}</td></tr>\n"

    html = f"""<!DOCTYPE html>
<html><head><title>{title}</title>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
table {{ border-collapse: collapse; width: 100%; max-width: 600px; }}
td, th {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
h1 {{ color: #333; }}
</style></head>
<body>
<h1>{title}</h1>
<p>Generated: {report.get('generated_at', '')}</p>
<table><tr><th>Metric</th><th>Value</th></tr>
{rows}
</table>
</body></html>"""

    with open(path, "w") as f:
        f.write(html)


if __name__ == "__main__":
    main()
