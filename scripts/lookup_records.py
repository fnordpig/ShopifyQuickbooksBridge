#!/usr/bin/env python3
"""
Cross-system record lookup and comparison.

Usage:
    python lookup_records.py --type customer --shopify shopify.json --qbo qbo.json
    python lookup_records.py --type order --shopify shopify.json --qbo qbo.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from utils import (
    normalize_shopify_customer,
    normalize_qbo_customer,
    normalize_shopify_order,
    normalize_qbo_invoice,
    compare_fields,
    parse_private_note,
)


def lookup_customers(shopify_customers: list[dict], qbo_customers: list[dict]) -> dict:
    """Cross-reference customers between Shopify and QBO by email."""
    # Build QBO lookup by email
    qbo_by_email: dict[str, dict] = {}
    for c in qbo_customers:
        email = (c.get("PrimaryEmailAddr") or {}).get("Address", "")
        if email:
            qbo_by_email[email.lower()] = c

    # Also build set of QBO emails that have been matched
    matched_qbo_emails: set[str] = set()
    records = []

    for sc in shopify_customers:
        norm_s = normalize_shopify_customer(sc)
        email = norm_s["email"].lower() if norm_s["email"] else ""

        if email and email in qbo_by_email:
            qbo = qbo_by_email[email]
            norm_q = normalize_qbo_customer(qbo)
            diffs = compare_fields(
                norm_s,
                norm_q,
                fields=[
                    "name",
                    "email",
                    "phone",
                    "address_line1",
                    "city",
                    "state",
                    "zip",
                    "tax_exempt",
                ],
            )
            matched_qbo_emails.add(email)
            has_diff = any(not d["match"] for d in diffs)
            records.append(
                {
                    "status": "matched",
                    "shopify": norm_s,
                    "qbo": norm_q,
                    "comparison": diffs,
                    "has_differences": has_diff,
                    "suggested_action": "review_differences" if has_diff else "none",
                }
            )
        else:
            records.append(
                {
                    "status": "missing_from_qbo",
                    "shopify": norm_s,
                    "qbo": None,
                    "comparison": None,
                    "suggested_action": "create_in_qbo",
                }
            )

    # Find orphaned QBO customers (not matched to any Shopify customer)
    shopify_emails = {
        (normalize_shopify_customer(c)["email"] or "").lower()
        for c in shopify_customers
    }
    for qbo in qbo_customers:
        email = ((qbo.get("PrimaryEmailAddr") or {}).get("Address", "") or "").lower()
        if email and email not in shopify_emails:
            records.append(
                {
                    "status": "orphaned_in_qbo",
                    "shopify": None,
                    "qbo": normalize_qbo_customer(qbo),
                    "comparison": None,
                    "suggested_action": "review_or_delete",
                }
            )
        elif not email and email not in matched_qbo_emails:
            # QBO customer with no email, check PrivateNote for shopify tag
            entries = parse_private_note(qbo.get("PrivateNote", ""))
            has_shopify_tag = any(e["tag"] == "shopify-sync" for e in entries)
            if has_shopify_tag:
                records.append(
                    {
                        "status": "orphaned_in_qbo",
                        "shopify": None,
                        "qbo": normalize_qbo_customer(qbo),
                        "comparison": None,
                        "suggested_action": "review_or_delete",
                    }
                )

    matched = sum(1 for r in records if r["status"] == "matched")
    return {
        "type": "customer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_shopify": len(shopify_customers),
            "total_qbo": len(qbo_customers),
            "matched": matched,
            "missing_from_qbo": sum(
                1 for r in records if r["status"] == "missing_from_qbo"
            ),
            "orphaned_in_qbo": sum(
                1 for r in records if r["status"] == "orphaned_in_qbo"
            ),
            "with_differences": sum(1 for r in records if r.get("has_differences")),
        },
        "records": records,
    }


def lookup_orders(shopify_orders: list[dict], qbo_invoices: list[dict]) -> dict:
    """Cross-reference orders between Shopify and QBO by order number (DocNumber)."""
    # Build QBO lookup by DocNumber
    qbo_by_doc: dict[str, dict] = {}
    for inv in qbo_invoices:
        doc = inv.get("DocNumber", "")
        if doc:
            qbo_by_doc[doc] = inv

    records = []
    matched_docs: set[str] = set()

    for order in shopify_orders:
        norm_s = normalize_shopify_order(order)
        # Expected DocNumber format: SH-{order_number}
        import re

        order_num = re.sub(r"[^0-9]", "", str(order.get("name", "")))
        doc_number = f"SH-{order_num}"

        if doc_number in qbo_by_doc:
            qbo = qbo_by_doc[doc_number]
            norm_q = normalize_qbo_invoice(qbo)
            diffs = compare_fields(
                norm_s,
                norm_q,
                fields=[
                    "date",
                    "customer_email",
                    "subtotal",
                    "tax_total",
                    "grand_total",
                    "shipping_total",
                    "discount_total",
                    "line_item_count",
                ],
            )
            matched_docs.add(doc_number)
            has_diff = any(not d["match"] for d in diffs)
            records.append(
                {
                    "status": "matched",
                    "doc_number": doc_number,
                    "shopify": norm_s,
                    "qbo": norm_q,
                    "comparison": diffs,
                    "has_differences": has_diff,
                    "suggested_action": "review_differences" if has_diff else "none",
                }
            )
        else:
            records.append(
                {
                    "status": "missing_from_qbo",
                    "doc_number": doc_number,
                    "shopify": norm_s,
                    "qbo": None,
                    "comparison": None,
                    "suggested_action": "sync_to_qbo",
                }
            )

    # Find orphaned QBO invoices
    for inv in qbo_invoices:
        doc = inv.get("DocNumber", "")
        if doc and doc not in matched_docs and doc.startswith("SH-"):
            records.append(
                {
                    "status": "orphaned_in_qbo",
                    "doc_number": doc,
                    "shopify": None,
                    "qbo": normalize_qbo_invoice(inv),
                    "comparison": None,
                    "suggested_action": "review_or_delete",
                }
            )

    matched = sum(1 for r in records if r["status"] == "matched")
    return {
        "type": "order",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_shopify": len(shopify_orders),
            "total_qbo": len(qbo_invoices),
            "matched": matched,
            "missing_from_qbo": sum(
                1 for r in records if r["status"] == "missing_from_qbo"
            ),
            "orphaned_in_qbo": sum(
                1 for r in records if r["status"] == "orphaned_in_qbo"
            ),
            "with_differences": sum(1 for r in records if r.get("has_differences")),
        },
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Cross-system record lookup and comparison"
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["customer", "order"],
        help="Record type to look up",
    )
    parser.add_argument("--shopify", required=True, help="Path to Shopify data JSON")
    parser.add_argument(
        "--qbo", required=False, default=None, help="Path to QBO data JSON"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="Output file (default: stdout)"
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print output JSON"
    )
    args = parser.parse_args()

    with open(args.shopify, "r") as f:
        shopify_data = json.load(f)
    if not isinstance(shopify_data, list):
        shopify_data = [shopify_data]

    qbo_data = []
    if args.qbo:
        try:
            with open(args.qbo, "r") as f:
                qbo_data = json.load(f)
            if not isinstance(qbo_data, list):
                qbo_data = [qbo_data]
        except FileNotFoundError:
            qbo_data = []

    if args.type == "customer":
        result = lookup_customers(shopify_data, qbo_data)
    else:
        result = lookup_orders(shopify_data, qbo_data)

    indent = 2 if args.pretty else None
    output_json = json.dumps(result, indent=indent, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        print(f"Output written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
