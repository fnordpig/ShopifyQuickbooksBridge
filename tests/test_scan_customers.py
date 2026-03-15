#!/usr/bin/env python3
"""Tests for scan_customers.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from scan_customers import scan_customers


class TestScanCustomers(unittest.TestCase):
    def _shopify(self):
        return [
            {
                "id": "gid://shopify/Customer/1001",
                "firstName": "Jane",
                "lastName": "Smith",
                "email": "jane@example.com",
                "phone": "+1-555-0100",
                "taxExempt": False,
                "tags": ["vip"],
                "defaultAddress": {
                    "address1": "123 Main St",
                    "city": "Seattle",
                    "provinceCode": "WA",
                    "zip": "98101",
                    "countryCodeV2": "US",
                },
            },
            {
                "id": "gid://shopify/Customer/1002",
                "firstName": "Bob",
                "lastName": "Lee",
                "email": "bob@example.com",
                "phone": "",
                "taxExempt": True,
                "tags": [],
                "defaultAddress": None,
            },
        ]

    def _qbo(self):
        return [
            {
                "Id": "101",
                "DisplayName": "Jane Smith",
                "PrimaryEmailAddr": {"Address": "jane@example.com"},
                "PrimaryPhone": {"FreeFormNumber": "+1-555-0100"},
                "BillAddr": {
                    "Line1": "123 Main St",
                    "City": "Seattle",
                    "CountrySubDivisionCode": "WA",
                    "PostalCode": "98101",
                    "Country": "US",
                },
                "Taxable": True,
                "PrivateNote": "[shopify-sync:gid://shopify/Customer/1001] Imported",
            },
        ]

    def test_missing_from_qbo(self):
        result = scan_customers(self._shopify(), self._qbo())
        missing = [i for i in result["issues"] if i["type"] == "missing_from_qbo"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["shopify_email"], "bob@example.com")

    def test_no_issues_for_matched(self):
        result = scan_customers(self._shopify()[:1], self._qbo())
        missing = [i for i in result["issues"] if i["type"] == "missing_from_qbo"]
        self.assertEqual(len(missing), 0)

    def test_orphaned_in_qbo(self):
        orphan_qbo = [
            {
                "Id": "999",
                "DisplayName": "Orphan User",
                "PrimaryEmailAddr": {"Address": "orphan@example.com"},
                "Taxable": True,
            }
        ]
        result = scan_customers(self._shopify(), self._qbo() + orphan_qbo)
        orphaned = [i for i in result["issues"] if i["type"] == "orphaned_in_qbo"]
        self.assertEqual(len(orphaned), 1)
        self.assertEqual(orphaned[0]["qbo_email"], "orphan@example.com")

    def test_data_mismatch(self):
        qbo = self._qbo()
        qbo[0]["PrimaryPhone"] = {"FreeFormNumber": "+1-555-9999"}
        result = scan_customers(self._shopify(), qbo)
        mismatch = [i for i in result["issues"] if i["type"] == "data_mismatch"]
        self.assertEqual(len(mismatch), 1)

    def test_sorted_by_severity(self):
        qbo = self._qbo()
        qbo[0]["PrimaryPhone"] = {"FreeFormNumber": "+1-555-9999"}
        orphan = [
            {
                "Id": "999",
                "DisplayName": "Orphan",
                "PrimaryEmailAddr": {"Address": "orphan@example.com"},
                "Taxable": True,
            }
        ]
        result = scan_customers(self._shopify(), qbo + orphan)
        # missing_from_qbo is high severity, should come before data_mismatch (medium)
        types = [i["type"] for i in result["issues"]]
        if "missing_from_qbo" in types and "data_mismatch" in types:
            self.assertLess(
                types.index("missing_from_qbo"),
                types.index("data_mismatch"),
            )

    def test_summary(self):
        result = scan_customers(self._shopify(), self._qbo())
        self.assertEqual(result["summary"]["total_shopify"], 2)
        self.assertEqual(result["summary"]["total_qbo"], 1)
        self.assertIn("total_issues", result["summary"])


if __name__ == "__main__":
    unittest.main()
