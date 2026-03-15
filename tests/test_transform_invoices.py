#!/usr/bin/env python3
"""Tests for transform_invoices.py"""

import json
import os
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from transform_invoices import (
    resolve_tax_code,
    parse_order_number,
    to_decimal,
    transform_line_item,
    transform_shipping_line,
    transform_discount,
    transform_tax_detail,
    transform_order,
)

TAX_MAP = {
    "mappings": {
        "US": {"State Tax": "TAX", "Sales Tax": "TAX", "WA State Tax": "TAX"},
        "CA": {"GST": "GST", "HST": "HST", "PST": "PST", "GST/HST": "HST"},
        "GB": {"VAT": "20.0% S"},
    },
    "defaults": {
        "taxable": "TAX",
        "exempt": "NON",
        "shipping": "NON",
        "unknown": "TAX",
    },
}


class TestResolveTaxCode(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(resolve_tax_code("State Tax", TAX_MAP), "TAX")

    def test_exact_match_canadian(self):
        self.assertEqual(resolve_tax_code("GST", TAX_MAP), "GST")
        self.assertEqual(resolve_tax_code("HST", TAX_MAP), "HST")
        self.assertEqual(resolve_tax_code("GST/HST", TAX_MAP), "HST")

    def test_exact_match_gb(self):
        self.assertEqual(resolve_tax_code("VAT", TAX_MAP), "20.0% S")

    def test_partial_match(self):
        # "WA" is in the title "WA State Tax" in the mapping
        self.assertEqual(resolve_tax_code("WA State Tax", TAX_MAP), "TAX")

    def test_exempt_keyword(self):
        self.assertEqual(resolve_tax_code("Tax Exempt", TAX_MAP), "NON")

    def test_free_keyword(self):
        self.assertEqual(resolve_tax_code("Tax Free", TAX_MAP), "NON")

    def test_zero_percent_keyword(self):
        self.assertEqual(resolve_tax_code("0% rate", TAX_MAP), "NON")

    def test_unknown_falls_back_to_tax(self):
        self.assertEqual(resolve_tax_code("Some Random Tax", TAX_MAP), "TAX")

    def test_empty_string_falls_back_to_unknown(self):
        self.assertEqual(resolve_tax_code("", TAX_MAP), "TAX")


class TestParseOrderNumber(unittest.TestCase):
    def test_hash_prefix(self):
        self.assertEqual(parse_order_number("#1001"), "1001")

    def test_no_prefix(self):
        self.assertEqual(parse_order_number("1001"), "1001")

    def test_letters_stripped(self):
        self.assertEqual(parse_order_number("ORD-1001"), "1001")

    def test_empty_string(self):
        self.assertEqual(parse_order_number(""), "")


class TestToDecimal(unittest.TestCase):
    def test_string_input(self):
        self.assertEqual(to_decimal("29.99"), Decimal("29.99"))

    def test_float_input(self):
        self.assertEqual(to_decimal(29.99), Decimal("29.99"))

    def test_int_input(self):
        self.assertEqual(to_decimal(30), Decimal("30"))

    def test_none_returns_zero(self):
        self.assertEqual(to_decimal(None), Decimal("0"))

    def test_zero_string(self):
        self.assertEqual(to_decimal("0"), Decimal("0"))


class TestTransformLineItem(unittest.TestCase):
    def _make_item(self, **overrides):
        base = {
            "title": "Premium Widget",
            "quantity": 2,
            "originalUnitPrice": "29.99",
            "taxLines": [{"title": "State Tax", "rate": "0.065", "price": "3.90"}],
            "variantId": "gid://shopify/Variant/100",
            "sku": "WIDGET-001",
        }
        base.update(overrides)
        return base

    def test_basic_line_item(self):
        result = transform_line_item(self._make_item(), TAX_MAP)
        self.assertEqual(result["DetailType"], "SalesItemLineDetail")
        self.assertEqual(result["Amount"], 59.98)
        self.assertEqual(result["Description"], "Premium Widget")
        detail = result["SalesItemLineDetail"]
        self.assertEqual(detail["Qty"], 2)
        self.assertEqual(detail["UnitPrice"], 29.99)
        self.assertEqual(detail["TaxCodeRef"]["value"], "TAX")

    def test_no_tax_lines_uses_non(self):
        result = transform_line_item(self._make_item(taxLines=[]), TAX_MAP)
        self.assertEqual(result["SalesItemLineDetail"]["TaxCodeRef"]["value"], "NON")

    def test_falls_back_to_price_field(self):
        item = self._make_item()
        del item["originalUnitPrice"]
        item["price"] = "15.00"
        result = transform_line_item(item, TAX_MAP)
        self.assertEqual(result["SalesItemLineDetail"]["UnitPrice"], 15.0)
        self.assertEqual(result["Amount"], 30.0)

    def test_quantity_defaults_to_1(self):
        item = self._make_item()
        del item["quantity"]
        result = transform_line_item(item, TAX_MAP)
        self.assertEqual(result["SalesItemLineDetail"]["Qty"], 1)

    def test_amount_rounded_to_two_decimals(self):
        item = self._make_item(originalUnitPrice="33.333", quantity=3)
        result = transform_line_item(item, TAX_MAP)
        self.assertEqual(
            result["Amount"], 100.0
        )  # 33.333 * 3 = 99.999, rounded to 100.00

    def test_shopify_metadata_preserved(self):
        result = transform_line_item(self._make_item(), TAX_MAP)
        self.assertEqual(result["_shopify_variant_id"], "gid://shopify/Variant/100")
        self.assertEqual(result["_shopify_sku"], "WIDGET-001")


class TestTransformShippingLine(unittest.TestCase):
    def test_basic_shipping(self):
        result = transform_shipping_line(
            {"title": "Standard Shipping", "price": "9.99"}
        )
        self.assertEqual(result["Amount"], 9.99)
        self.assertEqual(result["Description"], "Shipping: Standard Shipping")
        self.assertEqual(result["SalesItemLineDetail"]["TaxCodeRef"]["value"], "NON")
        self.assertEqual(result["SalesItemLineDetail"]["ItemRef"]["name"], "Shipping")

    def test_default_title(self):
        result = transform_shipping_line({"price": "5.00"})
        self.assertEqual(result["Description"], "Shipping: Standard")

    def test_zero_shipping(self):
        result = transform_shipping_line({"title": "Free Shipping", "price": "0"})
        self.assertEqual(result["Amount"], 0.0)


class TestTransformDiscount(unittest.TestCase):
    def test_positive_discount(self):
        result = transform_discount(Decimal("5.00"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["DetailType"], "DiscountLineDetail")
        self.assertEqual(result["Amount"], 5.0)
        self.assertFalse(result["DiscountLineDetail"]["PercentBased"])

    def test_zero_discount_returns_none(self):
        self.assertIsNone(transform_discount(Decimal("0")))

    def test_negative_discount_returns_none(self):
        self.assertIsNone(transform_discount(Decimal("-1")))


class TestTransformTaxDetail(unittest.TestCase):
    def test_single_tax_line(self):
        tax_lines = [{"title": "State Tax", "rate": "0.065", "price": "3.90"}]
        result = transform_tax_detail(tax_lines, TAX_MAP)
        self.assertEqual(result["TotalTax"], 3.90)
        self.assertEqual(len(result["TaxLine"]), 1)
        detail = result["TaxLine"][0]["TaxLineDetail"]
        self.assertEqual(detail["TaxPercent"], 6.5)
        self.assertTrue(detail["PercentBased"])

    def test_multiple_tax_lines(self):
        tax_lines = [
            {"title": "GST", "rate": "0.05", "price": "2.50"},
            {"title": "PST", "rate": "0.07", "price": "3.50"},
        ]
        result = transform_tax_detail(tax_lines, TAX_MAP)
        self.assertEqual(result["TotalTax"], 6.0)
        self.assertEqual(len(result["TaxLine"]), 2)
        self.assertEqual(
            result["TaxLine"][0]["TaxLineDetail"]["TaxRateRef"]["value"], "GST"
        )
        self.assertEqual(
            result["TaxLine"][1]["TaxLineDetail"]["TaxRateRef"]["value"], "PST"
        )

    def test_empty_tax_lines(self):
        result = transform_tax_detail([], TAX_MAP)
        self.assertEqual(result["TotalTax"], 0.0)
        self.assertEqual(result["TaxLine"], [])

    def test_rate_converted_to_percentage(self):
        tax_lines = [{"title": "Sales Tax", "rate": "0.1", "price": "10.00"}]
        result = transform_tax_detail(tax_lines, TAX_MAP)
        self.assertEqual(result["TaxLine"][0]["TaxLineDetail"]["TaxPercent"], 10.0)

    def test_shopify_tax_title_preserved(self):
        tax_lines = [{"title": "WA State Tax", "rate": "0.065", "price": "3.90"}]
        result = transform_tax_detail(tax_lines, TAX_MAP)
        self.assertEqual(result["TaxLine"][0]["_shopify_tax_title"], "WA State Tax")


class TestTransformOrder(unittest.TestCase):
    def _make_order(self, **overrides):
        base = {
            "id": "gid://shopify/Order/5001",
            "name": "#1001",
            "createdAt": "2025-03-15T10:30:00Z",
            "customer": {
                "firstName": "Jane",
                "lastName": "Smith",
                "email": "jane@example.com",
            },
            "lineItems": [
                {
                    "title": "Premium Widget",
                    "quantity": 2,
                    "originalUnitPrice": "29.99",
                    "taxLines": [
                        {"title": "State Tax", "rate": "0.065", "price": "3.90"}
                    ],
                }
            ],
            "shippingLines": [{"title": "Standard Shipping", "price": "9.99"}],
            "taxLines": [{"title": "State Tax", "rate": "0.065", "price": "3.90"}],
            "totalDiscounts": "5.00",
            "totalPrice": "68.87",
            "totalTax": "3.90",
            "subtotalPrice": "59.98",
            "financialStatus": "paid",
        }
        base.update(overrides)
        return base

    def test_doc_number_format(self):
        result = transform_order(self._make_order(), TAX_MAP)
        self.assertEqual(result["DocNumber"], "SH-1001")

    def test_txn_date_from_created_at(self):
        result = transform_order(self._make_order(), TAX_MAP)
        self.assertEqual(result["TxnDate"], "2025-03-15")

    def test_line_items_transformed(self):
        result = transform_order(self._make_order(), TAX_MAP)
        sales_lines = [
            line
            for line in result["Line"]
            if line["DetailType"] == "SalesItemLineDetail"
        ]
        # 1 product line + 1 shipping line
        self.assertEqual(len(sales_lines), 2)

    def test_shipping_line_included(self):
        result = transform_order(self._make_order(), TAX_MAP)
        shipping_lines = [
            line
            for line in result["Line"]
            if line.get("Description", "").startswith("Shipping:")
        ]
        self.assertEqual(len(shipping_lines), 1)
        self.assertEqual(shipping_lines[0]["Amount"], 9.99)

    def test_discount_line_included(self):
        result = transform_order(self._make_order(), TAX_MAP)
        discount_lines = [
            line
            for line in result["Line"]
            if line["DetailType"] == "DiscountLineDetail"
        ]
        self.assertEqual(len(discount_lines), 1)
        self.assertEqual(discount_lines[0]["Amount"], 5.0)

    def test_no_discount_when_zero(self):
        result = transform_order(self._make_order(totalDiscounts="0"), TAX_MAP)
        discount_lines = [
            line
            for line in result["Line"]
            if line["DetailType"] == "DiscountLineDetail"
        ]
        self.assertEqual(len(discount_lines), 0)

    def test_tax_detail_present(self):
        result = transform_order(self._make_order(), TAX_MAP)
        self.assertEqual(result["TxnTaxDetail"]["TotalTax"], 3.90)

    def test_private_note(self):
        result = transform_order(self._make_order(), TAX_MAP)
        self.assertIn("[shopify-sync:gid://shopify/Order/5001]", result["PrivateNote"])
        self.assertIn("Imported from Shopify order #1001", result["PrivateNote"])

    def test_private_note_contains_date(self):
        from datetime import datetime, timezone

        result = transform_order(self._make_order(), TAX_MAP)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertIn(f"on {today}", result["PrivateNote"])

    def test_customer_lookup_by_email(self):
        result = transform_order(self._make_order(), TAX_MAP)
        self.assertEqual(result["_customer_lookup"]["strategy"], "email")
        self.assertEqual(result["_customer_lookup"]["value"], "jane@example.com")

    def test_no_customer_lookup_without_email(self):
        order = self._make_order(customer={"firstName": "Guest", "lastName": ""})
        result = transform_order(order, TAX_MAP)
        self.assertNotIn("_customer_lookup", result)

    def test_validation_fields_present(self):
        result = transform_order(self._make_order(), TAX_MAP)
        v = result["_validation"]
        self.assertEqual(v["shopify_total_tax"], "3.90")
        self.assertEqual(v["shopify_total_discounts"], "5.00")
        self.assertEqual(v["shopify_financial_status"], "paid")

    def test_handles_edges_nodes_format(self):
        order = self._make_order(
            lineItems=[
                {
                    "node": {
                        "title": "Widget",
                        "quantity": 1,
                        "originalUnitPrice": "10.00",
                        "taxLines": [],
                    }
                }
            ]
        )
        result = transform_order(order, TAX_MAP)
        sales_lines = [
            line
            for line in result["Line"]
            if line["DetailType"] == "SalesItemLineDetail"
            and "Shipping" not in line.get("Description", "")
        ]
        self.assertEqual(sales_lines[0]["Description"], "Widget")

    def test_null_customer(self):
        result = transform_order(self._make_order(customer=None), TAX_MAP)
        self.assertEqual(result["_customer_email"], "")

    def test_total_discounts_set_format(self):
        order = self._make_order(totalDiscounts=None)
        order["totalDiscountsSet"] = {"shopMoney": {"amount": "7.50"}}
        result = transform_order(order, TAX_MAP)
        discount_lines = [
            line
            for line in result["Line"]
            if line["DetailType"] == "DiscountLineDetail"
        ]
        self.assertEqual(len(discount_lines), 1)
        self.assertEqual(discount_lines[0]["Amount"], 7.5)


class TestMainCLI(unittest.TestCase):
    def test_end_to_end_with_status_filter(self):
        orders = [
            {
                "id": "1",
                "name": "#1001",
                "createdAt": "2025-01-01T00:00:00Z",
                "customer": {"email": "a@x.com", "firstName": "A", "lastName": "B"},
                "lineItems": [
                    {
                        "title": "X",
                        "quantity": 1,
                        "originalUnitPrice": "10.00",
                        "taxLines": [],
                    }
                ],
                "shippingLines": [],
                "taxLines": [],
                "totalDiscounts": "0",
                "totalPrice": "10.00",
                "totalTax": "0",
                "subtotalPrice": "10.00",
                "financialStatus": "paid",
            },
            {
                "id": "2",
                "name": "#1002",
                "createdAt": "2025-01-02T00:00:00Z",
                "customer": {"email": "b@x.com", "firstName": "C", "lastName": "D"},
                "lineItems": [
                    {
                        "title": "Y",
                        "quantity": 1,
                        "originalUnitPrice": "20.00",
                        "taxLines": [],
                    }
                ],
                "shippingLines": [],
                "taxLines": [],
                "totalDiscounts": "0",
                "totalPrice": "20.00",
                "totalTax": "0",
                "subtotalPrice": "20.00",
                "financialStatus": "pending",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "orders.json")
            output_path = os.path.join(tmpdir, "invoices.json")
            tax_map_path = os.path.join(tmpdir, "tax-map.json")

            with open(input_path, "w") as f:
                json.dump(orders, f)
            with open(tax_map_path, "w") as f:
                json.dump(TAX_MAP, f)

            import sys

            old_argv = sys.argv
            sys.argv = [
                "transform_invoices.py",
                "--input",
                input_path,
                "--output",
                output_path,
                "--tax-map",
                tax_map_path,
                "--status-filter",
                "paid",
            ]
            try:
                from transform_invoices import main as invoice_main

                invoice_main()
            finally:
                sys.argv = old_argv

            with open(output_path) as f:
                output = json.load(f)

            # Only the paid order should be in output
            self.assertEqual(output["metadata"]["stats"]["total_output"], 1)
            self.assertEqual(output["metadata"]["stats"]["filtered_out"], 1)
            self.assertEqual(output["invoices"][0]["DocNumber"], "SH-1001")


if __name__ == "__main__":
    unittest.main()
