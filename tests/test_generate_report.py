#!/usr/bin/env python3
"""Tests for generate_report.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_report import (
    generate_sync_status_report,
    generate_reconciliation_report,
    generate_tax_report,
    generate_financial_report,
)


class TestSyncStatusReport(unittest.TestCase):
    def test_basic_sync_status(self):
        shopify_orders = [
            {"id": "1", "name": "#1001"},
            {"id": "2", "name": "#1002"},
            {"id": "3", "name": "#1003"},
        ]
        qbo_invoices = [
            {"DocNumber": "SH-1001", "PrivateNote": "[shopify-sync:1] Imported"},
            {"DocNumber": "SH-1002", "PrivateNote": "[shopify-sync:2] Imported"},
        ]
        result = generate_sync_status_report(shopify_orders, qbo_invoices)
        self.assertEqual(result["report_type"], "sync-status")
        self.assertEqual(result["data"]["total_shopify"], 3)
        self.assertEqual(result["data"]["total_qbo"], 2)
        self.assertEqual(result["data"]["synced"], 2)
        self.assertEqual(result["data"]["unsynced"], 1)

    def test_empty_inputs(self):
        result = generate_sync_status_report([], [])
        self.assertEqual(result["data"]["total_shopify"], 0)
        self.assertEqual(result["data"]["synced"], 0)


class TestReconciliationReport(unittest.TestCase):
    def test_basic_reconciliation(self):
        shopify_orders = [{
            "name": "#1001",
            "subtotalPrice": "100.00",
            "totalTax": "6.50",
            "totalPrice": "116.49",
            "totalDiscounts": "0",
            "shippingLines": [{"price": "9.99"}],
            "lineItems": [{"title": "X", "quantity": 1, "originalUnitPrice": "100.00", "taxLines": []}],
            "taxLines": [],
        }]
        qbo_invoices = [{
            "DocNumber": "SH-1001",
            "TotalAmt": 116.49,
            "TxnTaxDetail": {"TotalTax": 6.50, "TaxLine": []},
            "Line": [
                {"DetailType": "SalesItemLineDetail", "Amount": 100.00,
                 "SalesItemLineDetail": {"Qty": 1, "UnitPrice": 100.00}},
                {"DetailType": "SalesItemLineDetail", "Amount": 9.99,
                 "Description": "Shipping: Std",
                 "SalesItemLineDetail": {"Qty": 1, "UnitPrice": 9.99}},
            ],
        }]
        result = generate_reconciliation_report(shopify_orders, qbo_invoices)
        self.assertEqual(result["report_type"], "reconciliation")
        self.assertEqual(result["data"]["shopify_total_revenue"], "100.00")
        self.assertEqual(result["data"]["shopify_total_tax"], "6.50")

    def test_empty_data(self):
        result = generate_reconciliation_report([], [])
        self.assertEqual(result["data"]["shopify_order_count"], 0)


class TestTaxReport(unittest.TestCase):
    def test_groups_by_tax(self):
        qbo_invoices = [{
            "DocNumber": "SH-1001",
            "TxnTaxDetail": {
                "TotalTax": 6.50,
                "TaxLine": [
                    {"Amount": 6.50, "DetailType": "TaxLineDetail",
                     "TaxLineDetail": {"TaxRateRef": {"value": "TAX"},
                                       "TaxPercent": 6.5,
                                       "PercentBased": True, "NetAmountTaxable": 100.00},
                     "_shopify_tax_title": "State Tax"},
                ],
            },
            "Line": [
                {"DetailType": "SalesItemLineDetail", "Amount": 100.00,
                 "SalesItemLineDetail": {"Qty": 1, "UnitPrice": 100.00,
                                         "TaxCodeRef": {"value": "TAX"}}},
            ],
        }]
        result = generate_tax_report(qbo_invoices)
        self.assertEqual(result["report_type"], "tax")
        self.assertGreater(len(result["data"]["tax_groups"]), 0)
        self.assertEqual(result["data"]["total_tax_collected"], "6.50")


class TestFinancialReport(unittest.TestCase):
    def test_basic_financial(self):
        qbo_invoices = [{
            "DocNumber": "SH-1001",
            "TotalAmt": 116.49,
            "TxnTaxDetail": {"TotalTax": 6.50, "TaxLine": []},
            "Line": [
                {"DetailType": "SalesItemLineDetail", "Amount": 100.00,
                 "SalesItemLineDetail": {"Qty": 1, "UnitPrice": 100.00}},
                {"DetailType": "SalesItemLineDetail", "Amount": 9.99,
                 "Description": "Shipping: Std",
                 "SalesItemLineDetail": {"Qty": 1, "UnitPrice": 9.99}},
                {"DetailType": "DiscountLineDetail", "Amount": 0,
                 "DiscountLineDetail": {"PercentBased": False}},
            ],
        }]
        result = generate_financial_report(qbo_invoices)
        self.assertEqual(result["report_type"], "financial")
        self.assertIn("total_revenue", result["data"])
        self.assertIn("total_tax", result["data"])

    def test_empty(self):
        result = generate_financial_report([])
        self.assertEqual(result["data"]["invoice_count"], 0)


if __name__ == "__main__":
    unittest.main()
