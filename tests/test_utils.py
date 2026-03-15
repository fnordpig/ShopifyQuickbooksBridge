#!/usr/bin/env python3
"""Tests for utils.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from utils import (
    parse_private_note,
    normalize_shopify_customer,
    normalize_qbo_customer,
    normalize_shopify_order,
    normalize_qbo_invoice,
    compare_fields,
    format_currency,
)


class TestParsePrivateNote(unittest.TestCase):
    def test_parse_shopify_sync_tag(self):
        note = "[shopify-sync:gid://shopify/Customer/1001] Imported on 2026-03-14"
        result = parse_private_note(note)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tag"], "shopify-sync")
        self.assertEqual(result[0]["value"], "gid://shopify/Customer/1001")
        self.assertEqual(result[0]["detail"], "Imported on 2026-03-14")

    def test_parse_multiple_tags(self):
        note = (
            "[shopify-sync:gid://shopify/Order/5001] Imported on 2026-03-14\n"
            "[shopify-qbo:fix] Updated address on 2026-03-15"
        )
        result = parse_private_note(note)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["tag"], "shopify-sync")
        self.assertEqual(result[1]["tag"], "shopify-qbo")
        self.assertEqual(result[1]["value"], "fix")

    def test_parse_action_tags(self):
        note = "[shopify-qbo:delete] Deleted on 2026-03-14"
        result = parse_private_note(note)
        self.assertEqual(result[0]["tag"], "shopify-qbo")
        self.assertEqual(result[0]["value"], "delete")

    def test_empty_note(self):
        self.assertEqual(parse_private_note(""), [])
        self.assertEqual(parse_private_note("No tags here"), [])

    def test_none_note(self):
        self.assertEqual(parse_private_note(None), [])


class TestNormalizeShopifyCustomer(unittest.TestCase):
    def _make_customer(self):
        return {
            "id": "gid://shopify/Customer/1001",
            "firstName": "Jane",
            "lastName": "Smith",
            "email": "jane@example.com",
            "phone": "+1-555-0100",
            "taxExempt": False,
            "tags": ["wholesale", "vip"],
            "defaultAddress": {
                "address1": "123 Main St",
                "address2": "Suite 4",
                "city": "Seattle",
                "provinceCode": "WA",
                "zip": "98101",
                "countryCodeV2": "US",
            },
        }

    def test_normalizes_all_fields(self):
        result = normalize_shopify_customer(self._make_customer())
        self.assertEqual(result["name"], "Jane Smith")
        self.assertEqual(result["email"], "jane@example.com")
        self.assertEqual(result["phone"], "+1-555-0100")
        self.assertEqual(result["address_line1"], "123 Main St")
        self.assertEqual(result["city"], "Seattle")
        self.assertEqual(result["state"], "WA")
        self.assertEqual(result["zip"], "98101")
        self.assertEqual(result["country"], "US")
        self.assertFalse(result["tax_exempt"])
        self.assertEqual(result["shopify_id"], "gid://shopify/Customer/1001")

    def test_missing_address(self):
        c = self._make_customer()
        c["defaultAddress"] = None
        result = normalize_shopify_customer(c)
        self.assertEqual(result["address_line1"], "")
        self.assertEqual(result["city"], "")


class TestNormalizeQboCustomer(unittest.TestCase):
    def test_normalizes_qbo_fields(self):
        qbo = {
            "DisplayName": "Jane Smith",
            "PrimaryEmailAddr": {"Address": "jane@example.com"},
            "PrimaryPhone": {"FreeFormNumber": "+1-555-0100"},
            "BillAddr": {
                "Line1": "123 Main St",
                "Line2": "Suite 4",
                "City": "Seattle",
                "CountrySubDivisionCode": "WA",
                "PostalCode": "98101",
                "Country": "US",
            },
            "Taxable": True,
            "Notes": "Shopify ID: gid://shopify/Customer/1001",
            "PrivateNote": "[shopify-sync:gid://shopify/Customer/1001] Imported",
        }
        result = normalize_qbo_customer(qbo)
        self.assertEqual(result["name"], "Jane Smith")
        self.assertEqual(result["email"], "jane@example.com")
        self.assertEqual(result["phone"], "+1-555-0100")
        self.assertEqual(result["address_line1"], "123 Main St")
        self.assertEqual(result["city"], "Seattle")
        self.assertEqual(result["state"], "WA")
        self.assertEqual(result["zip"], "98101")
        self.assertFalse(result["tax_exempt"])

    def test_missing_optional_fields(self):
        qbo = {"DisplayName": "Guest"}
        result = normalize_qbo_customer(qbo)
        self.assertEqual(result["name"], "Guest")
        self.assertEqual(result["email"], "")
        self.assertEqual(result["phone"], "")


class TestNormalizeShopifyOrder(unittest.TestCase):
    def test_normalizes_order(self):
        order = {
            "name": "#1001",
            "createdAt": "2026-03-14T10:00:00Z",
            "customer": {"email": "jane@example.com", "firstName": "Jane", "lastName": "Smith"},
            "subtotalPrice": "59.98",
            "totalTax": "3.90",
            "totalPrice": "68.87",
            "totalDiscounts": "5.00",
            "taxLines": [{"title": "State Tax", "rate": "0.065", "price": "3.90"}],
            "lineItems": [
                {"title": "Widget", "quantity": 2, "originalUnitPrice": "29.99", "taxLines": []},
            ],
            "shippingLines": [{"title": "Standard", "price": "9.99"}],
        }
        result = normalize_shopify_order(order)
        self.assertEqual(result["customer_email"], "jane@example.com")
        self.assertEqual(result["subtotal"], "59.98")
        self.assertEqual(result["tax_total"], "3.90")
        self.assertEqual(result["grand_total"], "68.87")
        self.assertEqual(result["discount_total"], "5.00")
        self.assertEqual(result["shipping_total"], "9.99")
        self.assertEqual(result["line_item_count"], 1)


class TestNormalizeQboInvoice(unittest.TestCase):
    def test_normalizes_invoice(self):
        invoice = {
            "DocNumber": "SH-1001",
            "TxnDate": "2026-03-14",
            "TotalAmt": 68.87,
            "TxnTaxDetail": {"TotalTax": 3.90, "TaxLine": []},
            "Line": [
                {"DetailType": "SalesItemLineDetail", "Amount": 59.98,
                 "SalesItemLineDetail": {"Qty": 2, "UnitPrice": 29.99}},
                {"DetailType": "SalesItemLineDetail", "Amount": 9.99,
                 "Description": "Shipping: Standard",
                 "SalesItemLineDetail": {"Qty": 1, "UnitPrice": 9.99}},
            ],
            "_customer_email": "jane@example.com",
            "_customer_name": "Jane Smith",
        }
        result = normalize_qbo_invoice(invoice)
        self.assertEqual(result["customer_email"], "jane@example.com")
        self.assertEqual(result["grand_total"], "68.87")
        self.assertEqual(result["tax_total"], "3.90")


class TestCompareFields(unittest.TestCase):
    def test_matching_fields(self):
        a = {"name": "Jane", "email": "jane@x.com"}
        b = {"name": "Jane", "email": "jane@x.com"}
        result = compare_fields(a, b)
        self.assertTrue(all(r["match"] for r in result))

    def test_mismatched_fields(self):
        a = {"name": "Jane", "email": "jane@x.com"}
        b = {"name": "J.", "email": "jane@x.com"}
        result = compare_fields(a, b)
        name_cmp = [r for r in result if r["field"] == "name"][0]
        self.assertFalse(name_cmp["match"])
        self.assertEqual(name_cmp["a"], "Jane")
        self.assertEqual(name_cmp["b"], "J.")

    def test_subset_of_fields(self):
        a = {"name": "Jane", "email": "jane@x.com", "phone": "555"}
        b = {"name": "Jane", "email": "jane@x.com", "phone": "555"}
        result = compare_fields(a, b, fields=["name", "email"])
        self.assertEqual(len(result), 2)

    def test_missing_fields(self):
        a = {"name": "Jane"}
        b = {"name": "Jane", "email": "jane@x.com"}
        result = compare_fields(a, b, fields=["name", "email"])
        email_cmp = [r for r in result if r["field"] == "email"][0]
        self.assertFalse(email_cmp["match"])


class TestFormatCurrency(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(format_currency(1234.56), "$1,234.56")

    def test_zero(self):
        self.assertEqual(format_currency(0), "$0.00")

    def test_string_input(self):
        self.assertEqual(format_currency("999.9"), "$999.90")

    def test_large_number(self):
        self.assertEqual(format_currency(1000000), "$1,000,000.00")


if __name__ == "__main__":
    unittest.main()
