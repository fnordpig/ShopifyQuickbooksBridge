#!/usr/bin/env python3
"""
Expected state computation and diff between Shopify and QBO records.

Usage:
    python diff_records.py --type customer --shopify shopify.json --qbo qbo.json
    python diff_records.py --type invoice --shopify shopify.json --qbo qbo.json --tax-map tax-mapping.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from utils import (
    parse_private_note,
)
from transform_customers import transform_customer
from transform_invoices import transform_order


def _match_qbo_customer_to_shopify(
    qbo: dict, shopify_by_email: dict[str, dict]
) -> dict | None:
    """Find the Shopify customer that corresponds to a QBO customer."""
    email = (qbo.get("PrimaryEmailAddr") or {}).get("Address", "")
    if email and email.lower() in shopify_by_email:
        return shopify_by_email[email.lower()]

    # Try PrivateNote shopify-sync tag
    entries = parse_private_note(qbo.get("PrivateNote", ""))
    for entry in entries:
        if entry["tag"] == "shopify-sync":
            shopify_id = entry["value"]
            for sc in shopify_by_email.values():
                if sc.get("id") == shopify_id:
                    return sc
    return None


def _diff_customer_fields(expected: dict, actual: dict) -> list[dict]:
    """Compare expected QBO customer (from transform) with actual QBO customer."""
    fields_to_compare = [
        ("DisplayName", "DisplayName"),
        ("GivenName", "GivenName"),
        ("FamilyName", "FamilyName"),
        ("Taxable", "Taxable"),
    ]
    diffs = []

    for field, label in fields_to_compare:
        exp_val = expected.get(field, "")
        act_val = actual.get(field, "")
        if str(exp_val) != str(act_val):
            diffs.append(
                {"field": label, "expected": str(exp_val), "actual": str(act_val)}
            )

    # Compare email
    exp_email = (expected.get("PrimaryEmailAddr") or {}).get("Address", "")
    act_email = (actual.get("PrimaryEmailAddr") or {}).get("Address", "")
    if exp_email != act_email:
        diffs.append({"field": "Email", "expected": exp_email, "actual": act_email})

    # Compare phone
    exp_phone = (expected.get("PrimaryPhone") or {}).get("FreeFormNumber", "")
    act_phone = (actual.get("PrimaryPhone") or {}).get("FreeFormNumber", "")
    if exp_phone != act_phone:
        diffs.append({"field": "Phone", "expected": exp_phone, "actual": act_phone})

    # Compare address Line1
    exp_addr = (expected.get("BillAddr") or {}).get("Line1", "")
    act_addr = (actual.get("BillAddr") or {}).get("Line1", "")
    if exp_addr != act_addr:
        diffs.append({"field": "Address", "expected": exp_addr, "actual": act_addr})

    return diffs


def diff_customers(shopify_customers: list[dict], qbo_customers: list[dict]) -> dict:
    """Diff expected vs actual QBO state for customers."""
    shopify_by_email: dict[str, dict] = {}
    for sc in shopify_customers:
        email = (sc.get("email") or "").lower()
        if email:
            shopify_by_email[email] = sc

    # Build QBO lookup by email
    qbo_by_email: dict[str, dict] = {}
    for qbo in qbo_customers:
        email = ((qbo.get("PrimaryEmailAddr") or {}).get("Address", "") or "").lower()
        if email:
            qbo_by_email[email] = qbo

    records = []
    for sc in shopify_customers:
        email = (sc.get("email") or "").lower()
        expected = transform_customer(sc)

        if email and email in qbo_by_email:
            actual = qbo_by_email[email]
            diffs = _diff_customer_fields(expected, actual)
            status = "drifted" if diffs else "in_sync"
            records.append(
                {
                    "status": status,
                    "shopify_id": sc.get("id", ""),
                    "email": sc.get("email", ""),
                    "expected_display_name": expected.get("DisplayName", ""),
                    "actual_display_name": actual.get("DisplayName", ""),
                    "diffs": diffs,
                    "proposed_fix": expected if diffs else None,
                }
            )
        else:
            records.append(
                {
                    "status": "missing_from_qbo",
                    "shopify_id": sc.get("id", ""),
                    "email": sc.get("email", ""),
                    "expected": expected,
                    "diffs": [],
                    "proposed_fix": expected,
                }
            )

    in_sync = sum(1 for r in records if r["status"] == "in_sync")
    drifted = sum(1 for r in records if r["status"] == "drifted")
    missing = sum(1 for r in records if r["status"] == "missing_from_qbo")

    return {
        "type": "customer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_shopify": len(shopify_customers),
            "total_qbo": len(qbo_customers),
            "in_sync": in_sync,
            "drifted": drifted,
            "missing_from_qbo": missing,
        },
        "records": records,
    }


def _diff_invoice_lines(expected: dict, actual: dict) -> list[dict]:
    """Compare expected QBO invoice (from transform) with actual QBO invoice."""
    diffs = []

    # Compare DocNumber
    if expected.get("DocNumber") != actual.get("DocNumber"):
        diffs.append(
            {
                "field": "DocNumber",
                "expected": expected.get("DocNumber", ""),
                "actual": actual.get("DocNumber", ""),
            }
        )

    # Compare TxnDate
    if expected.get("TxnDate") != actual.get("TxnDate"):
        diffs.append(
            {
                "field": "TxnDate",
                "expected": expected.get("TxnDate", ""),
                "actual": actual.get("TxnDate", ""),
            }
        )

    # Compare line items (count and amounts)
    exp_sales = [
        line
        for line in expected.get("Line", [])
        if line.get("DetailType") == "SalesItemLineDetail"
    ]
    act_sales = [
        line
        for line in actual.get("Line", [])
        if line.get("DetailType") == "SalesItemLineDetail"
    ]
    if len(exp_sales) != len(act_sales):
        diffs.append(
            {
                "field": "LineItemCount",
                "expected": str(len(exp_sales)),
                "actual": str(len(act_sales)),
            }
        )

    # Compare individual line amounts
    for i, (el, al) in enumerate(zip(exp_sales, act_sales)):
        if abs(float(el.get("Amount", 0)) - float(al.get("Amount", 0))) > 0.01:
            diffs.append(
                {
                    "field": f"Line[{i}].Amount",
                    "expected": str(el.get("Amount", 0)),
                    "actual": str(al.get("Amount", 0)),
                }
            )
        exp_detail = el.get("SalesItemLineDetail", {})
        act_detail = al.get("SalesItemLineDetail", {})
        if (
            abs(
                float(exp_detail.get("UnitPrice", 0))
                - float(act_detail.get("UnitPrice", 0))
            )
            > 0.01
        ):
            diffs.append(
                {
                    "field": f"Line[{i}].UnitPrice",
                    "expected": str(exp_detail.get("UnitPrice", 0)),
                    "actual": str(act_detail.get("UnitPrice", 0)),
                }
            )

    # Compare tax
    exp_tax = expected.get("TxnTaxDetail", {}).get("TotalTax", 0)
    act_tax = actual.get("TxnTaxDetail", {}).get("TotalTax", 0)
    if abs(float(exp_tax) - float(act_tax)) > 0.01:
        diffs.append(
            {"field": "TotalTax", "expected": str(exp_tax), "actual": str(act_tax)}
        )

    # Compare discounts
    exp_disc = [
        line
        for line in expected.get("Line", [])
        if line.get("DetailType") == "DiscountLineDetail"
    ]
    act_disc = [
        line
        for line in actual.get("Line", [])
        if line.get("DetailType") == "DiscountLineDetail"
    ]
    exp_disc_total = sum(float(line.get("Amount", 0)) for line in exp_disc)
    act_disc_total = sum(float(line.get("Amount", 0)) for line in act_disc)
    if abs(exp_disc_total - act_disc_total) > 0.01:
        diffs.append(
            {
                "field": "DiscountTotal",
                "expected": str(exp_disc_total),
                "actual": str(act_disc_total),
            }
        )

    return diffs


def diff_invoices(
    shopify_orders: list[dict], qbo_invoices: list[dict], tax_map: dict
) -> dict:
    """Diff expected vs actual QBO state for invoices."""
    # Build QBO lookup by DocNumber
    qbo_by_doc: dict[str, dict] = {}
    for inv in qbo_invoices:
        doc = inv.get("DocNumber", "")
        if doc:
            qbo_by_doc[doc] = inv

    records = []
    for order in shopify_orders:
        expected = transform_order(order, tax_map)
        doc_number = expected.get("DocNumber", "")

        if doc_number in qbo_by_doc:
            actual = qbo_by_doc[doc_number]
            diffs = _diff_invoice_lines(expected, actual)
            status = "drifted" if diffs else "in_sync"
            records.append(
                {
                    "status": status,
                    "doc_number": doc_number,
                    "shopify_order_id": order.get("id", ""),
                    "shopify_order_name": order.get("name", ""),
                    "diffs": diffs,
                    "proposed_fix": expected if diffs else None,
                }
            )
        else:
            records.append(
                {
                    "status": "missing_from_qbo",
                    "doc_number": doc_number,
                    "shopify_order_id": order.get("id", ""),
                    "shopify_order_name": order.get("name", ""),
                    "expected": expected,
                    "diffs": [],
                    "proposed_fix": expected,
                }
            )

    in_sync = sum(1 for r in records if r["status"] == "in_sync")
    drifted = sum(1 for r in records if r["status"] == "drifted")
    missing = sum(1 for r in records if r["status"] == "missing_from_qbo")

    return {
        "type": "invoice",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_shopify": len(shopify_orders),
            "total_qbo": len(qbo_invoices),
            "in_sync": in_sync,
            "drifted": drifted,
            "missing_from_qbo": missing,
        },
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser(description="Diff expected vs actual QBO state")
    parser.add_argument(
        "--type",
        required=True,
        choices=["customer", "invoice"],
        help="Record type to diff",
    )
    parser.add_argument("--shopify", required=True, help="Path to Shopify data JSON")
    parser.add_argument("--qbo", required=True, help="Path to QBO data JSON")
    parser.add_argument(
        "--tax-map",
        default=None,
        help="Path to tax-mapping.json (required for invoice)",
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

    with open(args.qbo, "r") as f:
        qbo_data = json.load(f)
    if not isinstance(qbo_data, list):
        qbo_data = [qbo_data]

    if args.type == "customer":
        result = diff_customers(shopify_data, qbo_data)
    else:
        if not args.tax_map:
            print("Error: --tax-map required for invoice diffs", file=sys.stderr)
            sys.exit(1)
        with open(args.tax_map, "r") as f:
            tax_map = json.load(f)
        result = diff_invoices(shopify_data, qbo_data, tax_map)

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
