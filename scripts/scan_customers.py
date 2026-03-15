#!/usr/bin/env python3
"""
Cross-system customer scan: find mismatches, duplicates, orphans.

Usage:
    python scan_customers.py --shopify shopify_customers.json --qbo qbo_customers.json
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone

from utils import (
    normalize_shopify_customer,
    normalize_qbo_customer,
    compare_fields,
)

# Severity ordering: high issues first
SEVERITY_ORDER = {
    "missing_from_qbo": 0,
    "duplicate_email": 1,
    "data_mismatch": 2,
    "orphaned_in_qbo": 3,
    "qbo_only": 4,
}


def scan_customers(shopify_customers: list[dict], qbo_customers: list[dict]) -> dict:
    """Scan and cross-reference customers between systems.

    Categories: missing_from_qbo, duplicate_email, data_mismatch, orphaned_in_qbo, qbo_only.
    """
    issues: list[dict] = []

    # Build lookups by email
    shopify_by_email: dict[str, list[dict]] = {}
    for sc in shopify_customers:
        email = (sc.get("email") or "").lower()
        if email:
            shopify_by_email.setdefault(email, []).append(sc)

    qbo_by_email: dict[str, list[dict]] = {}
    for qbo in qbo_customers:
        email = ((qbo.get("PrimaryEmailAddr") or {}).get("Address", "") or "").lower()
        if email:
            qbo_by_email.setdefault(email, []).append(qbo)

    # Check for duplicates in Shopify
    for email, customers in shopify_by_email.items():
        if len(customers) > 1:
            issues.append({
                "type": "duplicate_email",
                "severity": "high",
                "shopify_email": email,
                "count": len(customers),
                "shopify_ids": [c.get("id", "") for c in customers],
                "message": f"Duplicate email '{email}' found in {len(customers)} Shopify customers",
            })

    # Check for duplicates in QBO
    for email, customers in qbo_by_email.items():
        if len(customers) > 1:
            issues.append({
                "type": "duplicate_email",
                "severity": "high",
                "qbo_email": email,
                "count": len(customers),
                "qbo_ids": [c.get("Id", "") for c in customers],
                "message": f"Duplicate email '{email}' found in {len(customers)} QBO customers",
            })

    # Cross-reference: find missing and mismatched
    matched_qbo_emails: set[str] = set()

    for email, shopify_list in shopify_by_email.items():
        sc = shopify_list[0]  # Use first for comparison
        norm_s = normalize_shopify_customer(sc)

        if email in qbo_by_email:
            qbo = qbo_by_email[email][0]
            norm_q = normalize_qbo_customer(qbo)
            matched_qbo_emails.add(email)

            # Check for data mismatches
            diffs = compare_fields(norm_s, norm_q, fields=[
                "name", "phone", "address_line1", "city", "state", "zip", "tax_exempt",
            ])
            mismatched = [d for d in diffs if not d["match"]]
            if mismatched:
                issues.append({
                    "type": "data_mismatch",
                    "severity": "medium",
                    "shopify_email": email,
                    "shopify_id": sc.get("id", ""),
                    "qbo_id": qbo.get("Id", ""),
                    "mismatched_fields": mismatched,
                    "message": f"Data mismatch for '{email}': {', '.join(d['field'] for d in mismatched)}",
                })
        else:
            issues.append({
                "type": "missing_from_qbo",
                "severity": "high",
                "shopify_email": email,
                "shopify_id": sc.get("id", ""),
                "shopify_name": norm_s["name"],
                "message": f"Customer '{norm_s['name']}' ({email}) not found in QBO",
            })

    # Shopify customers with no email
    for sc in shopify_customers:
        if not sc.get("email"):
            norm_s = normalize_shopify_customer(sc)
            issues.append({
                "type": "missing_from_qbo",
                "severity": "high",
                "shopify_email": "",
                "shopify_id": sc.get("id", ""),
                "shopify_name": norm_s["name"],
                "message": f"Customer '{norm_s['name']}' has no email, cannot match to QBO",
            })

    # Find orphaned QBO customers
    for email, qbo_list in qbo_by_email.items():
        if email not in shopify_by_email:
            qbo = qbo_list[0]
            norm_q = normalize_qbo_customer(qbo)
            issues.append({
                "type": "orphaned_in_qbo",
                "severity": "low",
                "qbo_email": email,
                "qbo_id": qbo.get("Id", ""),
                "qbo_name": norm_q["name"],
                "message": f"QBO customer '{norm_q['name']}' ({email}) has no Shopify match",
            })

    # Sort by severity
    issues.sort(key=lambda i: SEVERITY_ORDER.get(i["type"], 99))

    type_counts = Counter(i["type"] for i in issues)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_shopify": len(shopify_customers),
            "total_qbo": len(qbo_customers),
            "total_issues": len(issues),
            "missing_from_qbo": type_counts.get("missing_from_qbo", 0),
            "duplicate_email": type_counts.get("duplicate_email", 0),
            "data_mismatch": type_counts.get("data_mismatch", 0),
            "orphaned_in_qbo": type_counts.get("orphaned_in_qbo", 0),
            "qbo_only": type_counts.get("qbo_only", 0),
        },
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-system customer scan")
    parser.add_argument("--shopify", required=True, help="Path to Shopify customers JSON")
    parser.add_argument("--qbo", required=True, help="Path to QBO customers JSON")
    parser.add_argument("--output", "-o", default=None, help="Output file (default: stdout)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")
    args = parser.parse_args()

    with open(args.shopify, "r") as f:
        shopify_data = json.load(f)
    if not isinstance(shopify_data, list):
        shopify_data = [shopify_data]

    with open(args.qbo, "r") as f:
        qbo_data = json.load(f)
    if not isinstance(qbo_data, list):
        qbo_data = [qbo_data]

    result = scan_customers(shopify_data, qbo_data)

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
