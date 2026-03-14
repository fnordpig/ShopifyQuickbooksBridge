#!/usr/bin/env python3
"""
Shopify → QBO Sync Orchestrator

This script is the main entry point for the agentic sync pipeline.
It coordinates the full workflow:
  1. Extract data from Shopify (via MCP)
  2. Transform using mapping scripts
  3. Load into QBO (via MCP)
  4. Validate and generate audit report

In agentic mode, this serves as a reference for the Claude agent to follow.
The agent calls MCP tools directly and uses these scripts for transformation.

Usage (standalone for testing with pre-exported JSON):
    python orchestrator.py \
        --shopify-customers shopify_customers.json \
        --shopify-orders shopify_orders.json \
        --tax-map tax-mapping.json \
        --output-dir ./sync_output

Usage (with agent - the agent calls this for transform + validation only):
    python orchestrator.py \
        --mode transform-only \
        --shopify-customers shopify_customers.json \
        --shopify-orders shopify_orders.json \
        --tax-map tax-mapping.json \
        --output-dir ./sync_output
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_transform_customers(input_path: str, output_path: str) -> dict:
    """Run customer transformation and return stats."""
    import subprocess
    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)
    result = subprocess.run(
        [sys.executable, "transform_customers.py", "--input", input_path, "--output", output_path, "--pretty"],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"ERROR in customer transform: {result.stderr}", file=sys.stderr)
        return {"error": result.stderr}
    
    with open(output_path, "r") as f:
        data = json.load(f)
    return data.get("metadata", {}).get("stats", {})


def run_transform_invoices(input_path: str, output_path: str, tax_map_path: str, status_filter: str = "paid") -> dict:
    """Run invoice transformation and return stats."""
    import subprocess
    # Resolve all paths to absolute before passing to subprocess
    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)
    tax_map_path = os.path.abspath(tax_map_path)
    result = subprocess.run(
        [sys.executable, "transform_invoices.py",
         "--input", input_path, "--output", output_path,
         "--tax-map", tax_map_path, "--status-filter", status_filter, "--pretty"],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"ERROR in invoice transform: {result.stderr}", file=sys.stderr)
        return {"error": result.stderr}
    
    with open(output_path, "r") as f:
        data = json.load(f)
    return data.get("metadata", {}).get("stats", {})


def validate_sync(customer_output: str, invoice_output: str) -> dict:
    """Cross-validate transformed data for consistency."""
    issues = []
    
    with open(customer_output, "r") as f:
        customer_data = json.load(f)
    with open(invoice_output, "r") as f:
        invoice_data = json.load(f)
    
    customers = customer_data.get("customers", [])
    invoices = invoice_data.get("invoices", [])
    
    # Build customer email set
    customer_emails = {
        c.get("PrimaryEmailAddr", {}).get("Address", "").lower()
        for c in customers
        if c.get("PrimaryEmailAddr", {}).get("Address")
    }
    
    # Check that all invoice customer emails exist in customer set
    orphan_invoices = []
    for inv in invoices:
        email = inv.get("_customer_email", "").lower()
        if email and email not in customer_emails:
            orphan_invoices.append({
                "invoice": inv.get("DocNumber"),
                "email": email,
                "issue": "Customer email not in customer export set"
            })
    
    if orphan_invoices:
        issues.append({
            "type": "orphan_invoices",
            "count": len(orphan_invoices),
            "details": orphan_invoices[:10],  # First 10 only
            "note": "These invoices reference customers not in the export. They may already exist in QBO."
        })
    
    # Check for duplicate DocNumbers
    doc_numbers = [inv.get("DocNumber") for inv in invoices]
    seen = set()
    duplicates = []
    for dn in doc_numbers:
        if dn in seen:
            duplicates.append(dn)
        seen.add(dn)
    
    if duplicates:
        issues.append({
            "type": "duplicate_doc_numbers",
            "count": len(duplicates),
            "details": duplicates,
        })
    
    # Tax validation
    total_tax_from_invoices = sum(
        inv.get("TxnTaxDetail", {}).get("TotalTax", 0)
        for inv in invoices
    )
    
    total_shopify_tax = sum(
        float(inv.get("_validation", {}).get("shopify_total_tax", "0"))
        for inv in invoices
    )
    
    tax_discrepancy = abs(total_tax_from_invoices - total_shopify_tax)
    if tax_discrepancy > 0.01:
        issues.append({
            "type": "tax_discrepancy",
            "qbo_total_tax": round(total_tax_from_invoices, 2),
            "shopify_total_tax": round(total_shopify_tax, 2),
            "discrepancy": round(tax_discrepancy, 2),
        })
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "summary": {
            "customers": len(customers),
            "invoices": len(invoices),
            "customer_emails_available": len(customer_emails),
            "orphan_invoice_count": len(orphan_invoices),
            "total_tax_mapped": round(total_tax_from_invoices, 2),
            "total_shopify_tax_original": round(total_shopify_tax, 2),
            "tax_discrepancy": round(tax_discrepancy, 2),
        }
    }


def generate_audit_report(
    customer_stats: dict,
    invoice_stats: dict,
    validation: dict,
    output_dir: str,
) -> str:
    """Generate a comprehensive audit report."""
    report = {
        "report_type": "shopify_qbo_sync_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phases": {
            "extract": {
                "status": "complete",
                "note": "Data extracted from Shopify via MCP"
            },
            "transform": {
                "customers": customer_stats,
                "invoices": invoice_stats,
            },
            "validate": validation,
            "load": {
                "status": "pending",
                "note": "QBO load to be performed by agent via QBO MCP"
            }
        },
        "action_items": [],
    }
    
    # Generate action items from validation issues
    for issue in validation.get("issues", []):
        if issue["type"] == "orphan_invoices":
            report["action_items"].append(
                f"Check {issue['count']} invoices referencing customers not in export set"
            )
        elif issue["type"] == "duplicate_doc_numbers":
            report["action_items"].append(
                f"Resolve {issue['count']} duplicate document numbers before QBO import"
            )
        elif issue["type"] == "tax_discrepancy":
            report["action_items"].append(
                f"Review tax discrepancy of ${issue['discrepancy']:.2f} between Shopify and mapped QBO amounts"
            )
    
    if not report["action_items"]:
        report["action_items"].append("No issues found — ready for QBO import")
    
    # Write report
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"sync_audit_{timestamp}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    return report_path


def main():
    parser = argparse.ArgumentParser(description="Shopify → QBO Sync Orchestrator")
    parser.add_argument("--shopify-customers", required=True, help="Shopify customers JSON")
    parser.add_argument("--shopify-orders", required=True, help="Shopify orders JSON")
    parser.add_argument("--tax-map", required=True, help="Tax mapping config JSON")
    parser.add_argument("--output-dir", default="./sync_output", help="Output directory")
    parser.add_argument("--status-filter", default="paid", help="Order financial status filter")
    parser.add_argument("--mode", default="full", choices=["full", "transform-only"],
                        help="'full' for complete pipeline, 'transform-only' for just transform + validate")
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    customer_output = os.path.join(args.output_dir, "qbo_customers.json")
    invoice_output = os.path.join(args.output_dir, "qbo_invoices.json")
    
    print("=" * 60)
    print("Shopify → QBO Sync Pipeline")
    print("=" * 60)
    
    # Phase 2: Transform
    print("\n--- Phase 2: Transform Customers ---")
    customer_stats = run_transform_customers(args.shopify_customers, customer_output)
    
    print("\n--- Phase 2: Transform Invoices ---")
    invoice_stats = run_transform_invoices(args.shopify_orders, invoice_output, args.tax_map, args.status_filter)
    
    # Phase 3: Validate
    print("\n--- Phase 3: Validate ---")
    validation = validate_sync(customer_output, invoice_output)
    
    if validation["valid"]:
        print("✅ Validation passed — no issues found")
    else:
        print(f"⚠️  Validation found {len(validation['issues'])} issue(s):")
        for issue in validation["issues"]:
            print(f"  - {issue['type']}: {json.dumps(issue, default=str)[:200]}")
    
    # Phase 4: Audit Report
    print("\n--- Phase 4: Audit Report ---")
    report_path = generate_audit_report(customer_stats, invoice_stats, validation, args.output_dir)
    print(f"Audit report written to: {report_path}")
    
    # Summary
    print("\n" + "=" * 60)
    print("SYNC SUMMARY")
    print("=" * 60)
    print(f"  Customers transformed:  {customer_stats.get('total_output', '?')}")
    print(f"  Invoices transformed:   {invoice_stats.get('total_output', '?')}")
    print(f"  Total tax mapped:       ${validation['summary']['total_tax_mapped']:.2f}")
    print(f"  Tax discrepancy:        ${validation['summary']['tax_discrepancy']:.2f}")
    print(f"  Validation:             {'PASS' if validation['valid'] else 'ISSUES FOUND'}")
    print(f"\n  Output files:")
    print(f"    {customer_output}")
    print(f"    {invoice_output}")
    print(f"    {report_path}")
    
    if args.mode == "transform-only":
        print(f"\n  Mode: transform-only — QBO load deferred to agent")
        print(f"  Next step: Agent uses QBO MCP to upsert customers, then create invoices")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
