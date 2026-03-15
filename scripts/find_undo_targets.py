#!/usr/bin/env python3
"""
Find undo targets: parse PrivateNotes to find records matching an action for reversal.

Usage:
    python find_undo_targets.py --action sync --date 2026-03-14 --qbo-invoices inv.json --qbo-customers cust.json
    python find_undo_targets.py --action fix --qbo-invoices inv.json --qbo-customers cust.json
    python find_undo_targets.py --action sync --identifier SH-1001 --qbo-invoices inv.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from utils import parse_private_note


def find_undo_targets(
    action: str,
    date: str | None = None,
    identifier: str | None = None,
    qbo_invoices: list[dict] | None = None,
    qbo_customers: list[dict] | None = None,
) -> dict:
    """Find QBO records matching the given action for undo/reversal.

    Args:
        action: One of 'sync', 'fix', 'resolve-customers', 'delete'
        date: Optional date filter (YYYY-MM-DD)
        identifier: Optional identifier filter (e.g., SH-1001)
        qbo_invoices: List of QBO invoice dicts
        qbo_customers: List of QBO customer dicts
    """
    qbo_invoices = qbo_invoices or []
    qbo_customers = qbo_customers or []

    # Map action to tag patterns
    tag_map = {
        "sync": "shopify-sync",
        "fix": "shopify-qbo",
        "resolve-customers": "shopify-qbo",
        "delete": "shopify-qbo",
    }
    target_tag = tag_map.get(action, action)

    # For fix/delete/resolve-customers, also match by value
    value_filter = None
    if action in ("fix", "delete", "resolve-customers"):
        value_filter = action

    targets = []

    # Scan invoices
    for inv in qbo_invoices:
        private_note = inv.get("PrivateNote", "")
        entries = parse_private_note(private_note)

        for entry in entries:
            if entry["tag"] != target_tag:
                continue
            if value_filter and entry["value"] != value_filter:
                continue
            if date and date not in entry["detail"]:
                continue
            if identifier and identifier != inv.get("DocNumber", ""):
                continue

            targets.append(
                {
                    "entity_type": "invoice",
                    "id": inv.get("Id", ""),
                    "doc_number": inv.get("DocNumber", ""),
                    "display_name": inv.get("DocNumber", ""),
                    "total_amount": inv.get("TotalAmt", 0),
                    "action_tag": entry["tag"],
                    "action_value": entry["value"],
                    "action_detail": entry["detail"],
                    "private_note": private_note,
                }
            )
            break  # One match per record is enough

    # Scan customers
    for cust in qbo_customers:
        private_note = cust.get("PrivateNote", "")
        entries = parse_private_note(private_note)

        for entry in entries:
            if entry["tag"] != target_tag:
                continue
            if value_filter and entry["value"] != value_filter:
                continue
            if date and date not in entry["detail"]:
                continue
            if identifier:
                # For customers, identifier might match display name or shopify id
                if (
                    identifier != cust.get("DisplayName", "")
                    and identifier != entry["value"]
                ):
                    continue

            targets.append(
                {
                    "entity_type": "customer",
                    "id": cust.get("Id", ""),
                    "doc_number": "",
                    "display_name": cust.get("DisplayName", ""),
                    "action_tag": entry["tag"],
                    "action_value": entry["value"],
                    "action_detail": entry["detail"],
                    "private_note": private_note,
                }
            )
            break

    # Build reversal plan
    reversal_plan = []
    for target in targets:
        if action == "sync":
            reversal_plan.append(
                {
                    "target_id": target["id"],
                    "entity_type": target["entity_type"],
                    "display": target["display_name"] or target["doc_number"],
                    "reversal_action": "delete",
                    "description": f"Delete {target['entity_type']} '{target['display_name'] or target['doc_number']}' (undo sync)",
                }
            )
        elif action == "fix":
            reversal_plan.append(
                {
                    "target_id": target["id"],
                    "entity_type": target["entity_type"],
                    "display": target["display_name"] or target["doc_number"],
                    "reversal_action": "restore_original",
                    "description": f"Restore original state of {target['entity_type']} '{target['display_name'] or target['doc_number']}'",
                }
            )
        elif action == "delete":
            reversal_plan.append(
                {
                    "target_id": target["id"],
                    "entity_type": target["entity_type"],
                    "display": target["display_name"] or target["doc_number"],
                    "reversal_action": "undelete",
                    "description": f"Undelete {target['entity_type']} '{target['display_name'] or target['doc_number']}'",
                }
            )
        elif action == "resolve-customers":
            reversal_plan.append(
                {
                    "target_id": target["id"],
                    "entity_type": target["entity_type"],
                    "display": target["display_name"],
                    "reversal_action": "unresolve",
                    "description": f"Undo customer resolution for '{target['display_name']}'",
                }
            )

    return {
        "action": action,
        "date_filter": date,
        "identifier_filter": identifier,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_count": len(targets),
        "targets": targets,
        "reversal_plan": reversal_plan,
    }


def main():
    parser = argparse.ArgumentParser(description="Find undo targets by action and date")
    parser.add_argument(
        "--action",
        required=True,
        choices=["sync", "fix", "delete", "resolve-customers"],
        help="Action to undo",
    )
    parser.add_argument("--date", default=None, help="Date filter (YYYY-MM-DD)")
    parser.add_argument(
        "--identifier", default=None, help="Identifier filter (e.g., SH-1001)"
    )
    parser.add_argument(
        "--qbo-invoices", default=None, help="Path to QBO invoices JSON"
    )
    parser.add_argument(
        "--qbo-customers", default=None, help="Path to QBO customers JSON"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="Output file (default: stdout)"
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print output JSON"
    )
    args = parser.parse_args()

    qbo_invoices = []
    if args.qbo_invoices:
        with open(args.qbo_invoices, "r") as f:
            qbo_invoices = json.load(f)
        if not isinstance(qbo_invoices, list):
            qbo_invoices = [qbo_invoices]

    qbo_customers = []
    if args.qbo_customers:
        with open(args.qbo_customers, "r") as f:
            qbo_customers = json.load(f)
        if not isinstance(qbo_customers, list):
            qbo_customers = [qbo_customers]

    result = find_undo_targets(
        action=args.action,
        date=args.date,
        identifier=args.identifier,
        qbo_invoices=qbo_invoices,
        qbo_customers=qbo_customers,
    )

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
