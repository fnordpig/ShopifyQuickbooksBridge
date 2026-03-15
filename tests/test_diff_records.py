#!/usr/bin/env python3
"""Tests for diff_records.py"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from diff_records import diff_customers, diff_invoices

TAX_MAP = {
    "mappings": {
        "US": {"State Tax": "TAX"},
    },
    "defaults": {"taxable": "TAX", "exempt": "NON", "shipping": "NON", "unknown": "TAX"},
}


class TestDiffCustomers(unittest.TestCase):
    def _shopify_customer(self):
        return {
            "id": "gid://shopify/Customer/1001",
            "firstName": "Jane",
            "lastName": "Smith",
            "email": "jane@example.com",
            "phone": "+1-555-0100",
            "taxExempt": False,
            "tags": ["vip"],
            "defaultAddress": {
                "address1": "123 Main St", "city": "Seattle",
                "provinceCode": "WA", "zip": "98101", "countryCodeV2": "US",
            },
        }

    def _qbo_customer(self, **overrides):
        base = {
            "Id": "101",
            "DisplayName": "Jane Smith",
            "GivenName": "Jane",
            "FamilyName": "Smith",
            "PrimaryEmailAddr": {"Address": "jane@example.com"},
            "PrimaryPhone": {"FreeFormNumber": "+1-555-0100"},
            "BillAddr": {
                "Line1": "123 Main St", "City": "Seattle",
                "CountrySubDivisionCode": "WA", "PostalCode": "98101", "Country": "US",
            },
            "Taxable": True,
            "PrivateNote": "[shopify-sync:gid://shopify/Customer/1001] Imported",
        }
        base.update(overrides)
        return base

    def test_no_diff_when_matching(self):
        result = diff_customers([self._shopify_customer()], [self._qbo_customer()])
        in_sync = [r for r in result["records"] if r["status"] == "in_sync"]
        self.assertEqual(len(in_sync), 1)

    def test_detects_name_mismatch(self):
        qbo = self._qbo_customer(DisplayName="J. Smith")
        result = diff_customers([self._shopify_customer()], [qbo])
        drifted = [r for r in result["records"] if r["status"] == "drifted"]
        self.assertEqual(len(drifted), 1)
        fields = {d["field"] for d in drifted[0]["diffs"]}
        self.assertIn("DisplayName", fields)

    def test_missing_from_qbo(self):
        result = diff_customers([self._shopify_customer()], [])
        missing = [r for r in result["records"] if r["status"] == "missing_from_qbo"]
        self.assertEqual(len(missing), 1)

    def test_summary_counts(self):
        result = diff_customers([self._shopify_customer()], [self._qbo_customer()])
        self.assertEqual(result["summary"]["total_shopify"], 1)
        self.assertEqual(result["summary"]["in_sync"], 1)
        self.assertEqual(result["summary"]["drifted"], 0)


class TestDiffInvoices(unittest.TestCase):
    def _shopify_order(self):
        return {
            "id": "gid://shopify/Order/5001",
            "name": "#1001",
            "createdAt": "2026-03-14T10:00:00Z",
            "customer": {"email": "jane@example.com", "firstName": "Jane", "lastName": "Smith"},
            "lineItems": [
                {"title": "Widget", "quantity": 2, "originalUnitPrice": "29.99",
                 "taxLines": [{"title": "State Tax", "rate": "0.065", "price": "3.90"}]},
            ],
            "shippingLines": [{"title": "Standard", "price": "9.99"}],
            "taxLines": [{"title": "State Tax", "rate": "0.065", "price": "3.90"}],
            "totalDiscounts": "5.00",
            "totalPrice": "68.87",
            "totalTax": "3.90",
            "subtotalPrice": "59.98",
            "financialStatus": "paid",
        }

    def _qbo_invoice(self, **overrides):
        base = {
            "DocNumber": "SH-1001",
            "TxnDate": "2026-03-14",
            "TotalAmt": 68.87,
            "TxnTaxDetail": {"TotalTax": 3.90, "TaxLine": [
                {"Amount": 3.90, "DetailType": "TaxLineDetail",
                 "TaxLineDetail": {"TaxRateRef": {"value": "TAX"}, "TaxPercent": 6.5,
                                   "PercentBased": True, "NetAmountTaxable": 0}},
            ]},
            "Line": [
                {"DetailType": "SalesItemLineDetail", "Amount": 59.98,
                 "Description": "Widget",
                 "SalesItemLineDetail": {"Qty": 2, "UnitPrice": 29.99,
                                         "TaxCodeRef": {"value": "TAX"},
                                         "ItemRef": {"value": "1", "name": "Sales"}}},
                {"DetailType": "SalesItemLineDetail", "Amount": 9.99,
                 "Description": "Shipping: Standard",
                 "SalesItemLineDetail": {"Qty": 1, "UnitPrice": 9.99,
                                         "TaxCodeRef": {"value": "NON"},
                                         "ItemRef": {"value": "1", "name": "Shipping"}}},
                {"DetailType": "DiscountLineDetail", "Amount": 5.0,
                 "DiscountLineDetail": {"PercentBased": False}},
            ],
            "PrivateNote": "[shopify-sync:gid://shopify/Order/5001] Imported",
        }
        base.update(overrides)
        return base

    def test_no_diff_when_matching(self):
        result = diff_invoices([self._shopify_order()], [self._qbo_invoice()], TAX_MAP)
        in_sync = [r for r in result["records"] if r["status"] == "in_sync"]
        self.assertEqual(len(in_sync), 1)

    def test_detects_amount_mismatch(self):
        qbo = self._qbo_invoice()
        qbo["Line"][0]["Amount"] = 100.00
        qbo["Line"][0]["SalesItemLineDetail"]["UnitPrice"] = 50.00
        result = diff_invoices([self._shopify_order()], [qbo], TAX_MAP)
        drifted = [r for r in result["records"] if r["status"] == "drifted"]
        self.assertEqual(len(drifted), 1)

    def test_missing_from_qbo(self):
        result = diff_invoices([self._shopify_order()], [], TAX_MAP)
        missing = [r for r in result["records"] if r["status"] == "missing_from_qbo"]
        self.assertEqual(len(missing), 1)

    def test_summary(self):
        result = diff_invoices([self._shopify_order()], [self._qbo_invoice()], TAX_MAP)
        self.assertEqual(result["summary"]["total_shopify"], 1)


if __name__ == "__main__":
    unittest.main()
