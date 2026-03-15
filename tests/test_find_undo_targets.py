#!/usr/bin/env python3
"""Tests for find_undo_targets.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from find_undo_targets import find_undo_targets


class TestFindUndoTargets(unittest.TestCase):
    def _invoices(self):
        return [
            {
                "Id": "501",
                "DocNumber": "SH-1001",
                "TotalAmt": 68.87,
                "PrivateNote": "[shopify-sync:gid://shopify/Order/5001] Imported from Shopify order #1001 on 2026-03-14",
            },
            {
                "Id": "502",
                "DocNumber": "SH-1002",
                "TotalAmt": 42.00,
                "PrivateNote": "[shopify-sync:gid://shopify/Order/5002] Imported from Shopify order #1002 on 2026-03-15",
            },
            {
                "Id": "503",
                "DocNumber": "SH-1003",
                "TotalAmt": 100.00,
                "PrivateNote": "[shopify-qbo:fix] Updated tax on 2026-03-15",
            },
        ]

    def _customers(self):
        return [
            {
                "Id": "101",
                "DisplayName": "Jane Smith",
                "PrivateNote": "[shopify-sync:gid://shopify/Customer/1001] Imported on 2026-03-14",
            },
            {
                "Id": "102",
                "DisplayName": "Bob Lee",
                "PrivateNote": "[shopify-qbo:delete] Marked for deletion on 2026-03-14",
            },
        ]

    def test_find_sync_targets_by_date(self):
        result = find_undo_targets(
            action="sync",
            date="2026-03-14",
            qbo_invoices=self._invoices(),
            qbo_customers=self._customers(),
        )
        targets = result["targets"]
        # Should find invoice SH-1001 and customer Jane Smith (both synced on 2026-03-14)
        ids = [t["id"] for t in targets]
        self.assertIn("501", ids)
        self.assertIn("101", ids)

    def test_find_fix_targets(self):
        result = find_undo_targets(
            action="fix",
            date=None,
            qbo_invoices=self._invoices(),
            qbo_customers=self._customers(),
        )
        targets = result["targets"]
        ids = [t["id"] for t in targets]
        self.assertIn("503", ids)

    def test_find_delete_targets(self):
        result = find_undo_targets(
            action="delete",
            date=None,
            qbo_invoices=self._invoices(),
            qbo_customers=self._customers(),
        )
        targets = result["targets"]
        ids = [t["id"] for t in targets]
        self.assertIn("102", ids)

    def test_find_by_identifier(self):
        result = find_undo_targets(
            action="sync",
            date=None,
            identifier="SH-1001",
            qbo_invoices=self._invoices(),
            qbo_customers=self._customers(),
        )
        targets = result["targets"]
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["doc_number"], "SH-1001")

    def test_reversal_plan(self):
        result = find_undo_targets(
            action="sync",
            date="2026-03-14",
            qbo_invoices=self._invoices(),
            qbo_customers=self._customers(),
        )
        self.assertIn("reversal_plan", result)
        self.assertGreater(len(result["reversal_plan"]), 0)

    def test_empty_inputs(self):
        result = find_undo_targets(
            action="sync", date="2026-03-14", qbo_invoices=[], qbo_customers=[]
        )
        self.assertEqual(len(result["targets"]), 0)


if __name__ == "__main__":
    unittest.main()
