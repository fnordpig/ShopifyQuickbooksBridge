#!/usr/bin/env python3
"""
Transform Shopify customers to QuickBooks Online customer format.

Usage:
    python transform_customers.py --input shopify_customers.json --output qbo_customers.json
    
Input: JSON array of Shopify customer objects (from Shopify MCP get-customers)
Output: JSON array of QBO-ready customer objects
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any


def transform_address(shopify_addr: dict | None) -> dict | None:
    """Convert Shopify address to QBO BillAddr format."""
    if not shopify_addr:
        return None
    
    return {
        "Line1": shopify_addr.get("address1", ""),
        "Line2": shopify_addr.get("address2", ""),
        "City": shopify_addr.get("city", ""),
        "CountrySubDivisionCode": shopify_addr.get("provinceCode") or shopify_addr.get("province", ""),
        "PostalCode": shopify_addr.get("zip", ""),
        "Country": shopify_addr.get("countryCodeV2") or shopify_addr.get("country", ""),
    }


def transform_customer(shopify_customer: dict) -> dict:
    """Transform a single Shopify customer to QBO format."""
    first_name = shopify_customer.get("firstName", "") or ""
    last_name = shopify_customer.get("lastName", "") or ""
    email = shopify_customer.get("email", "")
    phone = shopify_customer.get("phone", "")
    
    # Build display name (must be unique in QBO)
    display_name = f"{first_name} {last_name}".strip()
    if not display_name:
        display_name = email or f"Shopify Customer {shopify_customer.get('id', 'unknown')}"
    
    # Build tags/notes
    tags = shopify_customer.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    
    notes_parts = []
    if tags:
        notes_parts.append(f"Shopify tags: {', '.join(tags)}")
    
    shopify_id = shopify_customer.get("id", "")
    if shopify_id:
        notes_parts.append(f"Shopify ID: {shopify_id}")
    
    # Tax exemption: Shopify taxExempt=true → QBO Taxable=false
    tax_exempt = shopify_customer.get("taxExempt", False)
    
    # Address
    default_address = shopify_customer.get("defaultAddress") or {}
    if not default_address:
        # Try first address from addresses array
        addresses = shopify_customer.get("addresses", [])
        if addresses:
            default_address = addresses[0]
    
    qbo_customer: dict[str, Any] = {
        "DisplayName": display_name,
        "GivenName": first_name,
        "FamilyName": last_name,
        "Taxable": not tax_exempt,
        "_shopify_id": shopify_id,
        "_shopify_email": email,
        "_sync_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if email:
        qbo_customer["PrimaryEmailAddr"] = {"Address": email}
    
    if phone:
        qbo_customer["PrimaryPhone"] = {"FreeFormNumber": phone}
    
    bill_addr = transform_address(default_address)
    if bill_addr and bill_addr.get("Line1"):
        qbo_customer["BillAddr"] = bill_addr
    
    if notes_parts:
        qbo_customer["Notes"] = " | ".join(notes_parts)
    
    return qbo_customer


def deduplicate_display_names(customers: list[dict]) -> list[dict]:
    """Ensure DisplayName uniqueness by appending email for collisions."""
    seen: dict[str, int] = {}
    
    for customer in customers:
        name = customer["DisplayName"]
        if name in seen:
            seen[name] += 1
            email = customer.get("PrimaryEmailAddr", {}).get("Address", "")
            if email:
                customer["DisplayName"] = f"{name} ({email})"
            else:
                customer["DisplayName"] = f"{name} #{seen[name]}"
        else:
            seen[name] = 1
    
    return customers


def main():
    parser = argparse.ArgumentParser(description="Transform Shopify customers to QBO format")
    parser.add_argument("--input", "-i", required=True, help="Path to Shopify customers JSON")
    parser.add_argument("--output", "-o", required=True, help="Path to write QBO customers JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")
    args = parser.parse_args()
    
    # Read input
    with open(args.input, "r") as f:
        shopify_customers = json.load(f)
    
    if not isinstance(shopify_customers, list):
        shopify_customers = [shopify_customers]
    
    # Transform
    qbo_customers = [transform_customer(c) for c in shopify_customers]
    
    # Deduplicate display names
    qbo_customers = deduplicate_display_names(qbo_customers)
    
    # Summary
    stats = {
        "total_input": len(shopify_customers),
        "total_output": len(qbo_customers),
        "tax_exempt_count": sum(1 for c in qbo_customers if not c.get("Taxable", True)),
        "missing_email": sum(1 for c in qbo_customers if "PrimaryEmailAddr" not in c),
        "missing_address": sum(1 for c in qbo_customers if "BillAddr" not in c),
    }
    
    # Write output
    output = {
        "metadata": {
            "source": "shopify",
            "target": "quickbooks_online",
            "entity": "customer",
            "transform_version": "1.0",
            "transformed_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
        },
        "customers": qbo_customers,
    }
    
    indent = 2 if args.pretty else None
    with open(args.output, "w") as f:
        json.dump(output, f, indent=indent)
    
    print(f"Transformed {stats['total_input']} Shopify customers → {stats['total_output']} QBO customers")
    print(f"  Tax exempt: {stats['tax_exempt_count']}")
    print(f"  Missing email: {stats['missing_email']}")
    print(f"  Missing address: {stats['missing_address']}")
    print(f"Output written to: {args.output}")


if __name__ == "__main__":
    main()
