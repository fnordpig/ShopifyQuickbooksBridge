#!/usr/bin/env python3
"""Tests for lookup_records.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from lookup_records import lookup_customers, lookup_orders


class TestLookupCustomers(unittest.TestCase):
    def _shopify_customers(self):
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

    def _qbo_customers(self):
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

    def test_matched_customer(self):
        result = lookup_customers(self._shopify_customers(), self._qbo_customers())
        matched = [r for r in result["records"] if r["status"] == "matched"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["shopify"]["email"], "jane@example.com")

    def test_missing_from_qbo(self):
        result = lookup_customers(self._shopify_customers(), self._qbo_customers())
        missing = [r for r in result["records"] if r["status"] == "missing_from_qbo"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["shopify"]["email"], "bob@example.com")

    def test_orphaned_in_qbo(self):
        result = lookup_customers([], self._qbo_customers())
        orphaned = [r for r in result["records"] if r["status"] == "orphaned_in_qbo"]
        self.assertEqual(len(orphaned), 1)

    def test_empty_qbo(self):
        result = lookup_customers(self._shopify_customers(), [])
        missing = [r for r in result["records"] if r["status"] == "missing_from_qbo"]
        self.assertEqual(len(missing), 2)

    def test_summary_counts(self):
        result = lookup_customers(self._shopify_customers(), self._qbo_customers())
        self.assertEqual(result["summary"]["total_shopify"], 2)
        self.assertEqual(result["summary"]["total_qbo"], 1)
        self.assertEqual(result["summary"]["matched"], 1)


class TestLookupOrders(unittest.TestCase):
    def test_matched_order(self):
        shopify = [
            {
                "id": "gid://shopify/Order/5001",
                "name": "#1001",
                "createdAt": "2026-03-14T10:00:00Z",
                "customer": {
                    "email": "jane@example.com",
                    "firstName": "Jane",
                    "lastName": "Smith",
                },
                "subtotalPrice": "59.98",
                "totalTax": "3.90",
                "totalPrice": "68.87",
                "totalDiscounts": "5.00",
                "taxLines": [{"title": "Tax", "rate": "0.065", "price": "3.90"}],
                "lineItems": [
                    {
                        "title": "W",
                        "quantity": 2,
                        "originalUnitPrice": "29.99",
                        "taxLines": [],
                    }
                ],
                "shippingLines": [{"price": "9.99"}],
            }
        ]
        qbo = [
            {
                "DocNumber": "SH-1001",
                "TxnDate": "2026-03-14",
                "TotalAmt": 68.87,
                "TxnTaxDetail": {"TotalTax": 3.90, "TaxLine": []},
                "Line": [
                    {
                        "DetailType": "SalesItemLineDetail",
                        "Amount": 59.98,
                        "SalesItemLineDetail": {"Qty": 2, "UnitPrice": 29.99},
                    }
                ],
                "_customer_email": "jane@example.com",
                "_customer_name": "Jane Smith",
                "PrivateNote": "[shopify-sync:gid://shopify/Order/5001] Imported",
            }
        ]
        result = lookup_orders(shopify, qbo)
        matched = [r for r in result["records"] if r["status"] == "matched"]
        self.assertEqual(len(matched), 1)

    def test_missing_order(self):
        shopify = [
            {
                "id": "gid://shopify/Order/5001",
                "name": "#1001",
                "createdAt": "2026-03-14T10:00:00Z",
                "customer": {"email": "j@x.com", "firstName": "J", "lastName": "S"},
                "subtotalPrice": "10.00",
                "totalTax": "0",
                "totalPrice": "10.00",
                "totalDiscounts": "0",
                "taxLines": [],
                "lineItems": [
                    {
                        "title": "X",
                        "quantity": 1,
                        "originalUnitPrice": "10.00",
                        "taxLines": [],
                    }
                ],
                "shippingLines": [],
            }
        ]
        result = lookup_orders(shopify, [])
        missing = [r for r in result["records"] if r["status"] == "missing_from_qbo"]
        self.assertEqual(len(missing), 1)


if __name__ == "__main__":
    unittest.main()
