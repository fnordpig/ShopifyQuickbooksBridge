#!/usr/bin/env python3
"""Tests for transform_customers.py"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from transform_customers import (
    transform_address,
    transform_customer,
    deduplicate_display_names,
)


class TestTransformAddress(unittest.TestCase):
    def test_returns_none_for_none_input(self):
        self.assertIsNone(transform_address(None))

    def test_returns_none_for_empty_dict(self):
        # Empty dict is falsy, should return None
        self.assertIsNone(transform_address({}))

    def test_maps_all_fields(self):
        shopify_addr = {
            "address1": "123 Main St",
            "address2": "Suite 4",
            "city": "Seattle",
            "provinceCode": "WA",
            "province": "Washington",
            "zip": "98101",
            "countryCodeV2": "US",
            "country": "United States",
        }
        result = transform_address(shopify_addr)
        self.assertEqual(result["Line1"], "123 Main St")
        self.assertEqual(result["Line2"], "Suite 4")
        self.assertEqual(result["City"], "Seattle")
        self.assertEqual(result["CountrySubDivisionCode"], "WA")
        self.assertEqual(result["PostalCode"], "98101")
        self.assertEqual(result["Country"], "US")

    def test_prefers_province_code_over_province(self):
        addr = {"provinceCode": "WA", "province": "Washington"}
        result = transform_address(addr)
        self.assertEqual(result["CountrySubDivisionCode"], "WA")

    def test_falls_back_to_province_when_no_province_code(self):
        addr = {"province": "Washington"}
        result = transform_address(addr)
        self.assertEqual(result["CountrySubDivisionCode"], "Washington")

    def test_prefers_country_code_v2_over_country(self):
        addr = {"countryCodeV2": "US", "country": "United States"}
        result = transform_address(addr)
        self.assertEqual(result["Country"], "US")

    def test_falls_back_to_country_when_no_code_v2(self):
        addr = {"country": "United States"}
        result = transform_address(addr)
        self.assertEqual(result["Country"], "United States")

    def test_missing_fields_default_to_empty_string(self):
        result = transform_address({"address1": "123 Main"})
        self.assertEqual(result["Line2"], "")
        self.assertEqual(result["City"], "")
        self.assertEqual(result["PostalCode"], "")


class TestTransformCustomer(unittest.TestCase):
    def _make_customer(self, **overrides):
        base = {
            "id": "gid://shopify/Customer/1001",
            "firstName": "Jane",
            "lastName": "Smith",
            "email": "jane@example.com",
            "phone": "+1-555-0100",
            "taxExempt": False,
            "tags": ["wholesale", "vip"],
            "defaultAddress": {
                "address1": "123 Main St",
                "city": "Seattle",
                "provinceCode": "WA",
                "zip": "98101",
                "countryCodeV2": "US",
            },
        }
        base.update(overrides)
        return base

    def test_display_name_from_first_last(self):
        result = transform_customer(self._make_customer())
        self.assertEqual(result["DisplayName"], "Jane Smith")

    def test_display_name_falls_back_to_email(self):
        result = transform_customer(self._make_customer(firstName="", lastName=""))
        self.assertEqual(result["DisplayName"], "jane@example.com")

    def test_display_name_falls_back_to_shopify_customer_id(self):
        result = transform_customer(self._make_customer(
            firstName="", lastName="", email=""
        ))
        self.assertEqual(result["DisplayName"], "Shopify Customer gid://shopify/Customer/1001")

    def test_display_name_handles_none_names(self):
        result = transform_customer(self._make_customer(firstName=None, lastName=None))
        self.assertEqual(result["DisplayName"], "jane@example.com")

    def test_given_and_family_name(self):
        result = transform_customer(self._make_customer())
        self.assertEqual(result["GivenName"], "Jane")
        self.assertEqual(result["FamilyName"], "Smith")

    def test_tax_exempt_true_makes_taxable_false(self):
        result = transform_customer(self._make_customer(taxExempt=True))
        self.assertFalse(result["Taxable"])

    def test_tax_exempt_false_makes_taxable_true(self):
        result = transform_customer(self._make_customer(taxExempt=False))
        self.assertTrue(result["Taxable"])

    def test_email_set_as_primary_email_addr(self):
        result = transform_customer(self._make_customer())
        self.assertEqual(result["PrimaryEmailAddr"]["Address"], "jane@example.com")

    def test_no_email_omits_primary_email_addr(self):
        result = transform_customer(self._make_customer(email=""))
        self.assertNotIn("PrimaryEmailAddr", result)

    def test_phone_set_as_primary_phone(self):
        result = transform_customer(self._make_customer())
        self.assertEqual(result["PrimaryPhone"]["FreeFormNumber"], "+1-555-0100")

    def test_no_phone_omits_primary_phone(self):
        result = transform_customer(self._make_customer(phone=""))
        self.assertNotIn("PrimaryPhone", result)

    def test_address_mapped_to_bill_addr(self):
        result = transform_customer(self._make_customer())
        self.assertIn("BillAddr", result)
        self.assertEqual(result["BillAddr"]["Line1"], "123 Main St")

    def test_no_address_omits_bill_addr(self):
        result = transform_customer(self._make_customer(defaultAddress=None))
        self.assertNotIn("BillAddr", result)

    def test_falls_back_to_addresses_array(self):
        customer = self._make_customer(
            defaultAddress=None,
            addresses=[{"address1": "456 Oak Ave", "city": "Portland"}],
        )
        result = transform_customer(customer)
        self.assertIn("BillAddr", result)
        self.assertEqual(result["BillAddr"]["Line1"], "456 Oak Ave")

    def test_tags_as_list_in_notes(self):
        result = transform_customer(self._make_customer(tags=["wholesale", "vip"]))
        self.assertIn("Shopify tags: wholesale, vip", result["Notes"])

    def test_tags_as_comma_string_in_notes(self):
        result = transform_customer(self._make_customer(tags="wholesale, vip"))
        self.assertIn("Shopify tags: wholesale, vip", result["Notes"])

    def test_shopify_id_in_notes(self):
        result = transform_customer(self._make_customer())
        self.assertIn("Shopify ID: gid://shopify/Customer/1001", result["Notes"])

    def test_metadata_fields_present(self):
        result = transform_customer(self._make_customer())
        self.assertEqual(result["_shopify_id"], "gid://shopify/Customer/1001")
        self.assertEqual(result["_shopify_email"], "jane@example.com")
        self.assertIn("_sync_timestamp", result)

    def test_private_note_contains_provenance_tag(self):
        result = transform_customer(self._make_customer())
        self.assertIn("PrivateNote", result)
        self.assertIn("[shopify-sync:gid://shopify/Customer/1001]", result["PrivateNote"])

    def test_private_note_contains_imported_on_date(self):
        result = transform_customer(self._make_customer())
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertIn(f"Imported on {today}", result["PrivateNote"])


class TestDeduplicateDisplayNames(unittest.TestCase):
    def test_no_duplicates_unchanged(self):
        customers = [
            {"DisplayName": "Alice", "PrimaryEmailAddr": {"Address": "a@x.com"}},
            {"DisplayName": "Bob", "PrimaryEmailAddr": {"Address": "b@x.com"}},
        ]
        result = deduplicate_display_names(customers)
        self.assertEqual(result[0]["DisplayName"], "Alice")
        self.assertEqual(result[1]["DisplayName"], "Bob")

    def test_duplicate_appends_email(self):
        customers = [
            {"DisplayName": "Jane Smith", "PrimaryEmailAddr": {"Address": "jane1@x.com"}},
            {"DisplayName": "Jane Smith", "PrimaryEmailAddr": {"Address": "jane2@x.com"}},
        ]
        result = deduplicate_display_names(customers)
        # First keeps original name
        self.assertEqual(result[0]["DisplayName"], "Jane Smith")
        # Second gets email appended
        self.assertEqual(result[1]["DisplayName"], "Jane Smith (jane2@x.com)")

    def test_duplicate_without_email_appends_number(self):
        customers = [
            {"DisplayName": "No Email"},
            {"DisplayName": "No Email"},
        ]
        result = deduplicate_display_names(customers)
        self.assertEqual(result[0]["DisplayName"], "No Email")
        self.assertEqual(result[1]["DisplayName"], "No Email #2")

    def test_three_duplicates(self):
        customers = [
            {"DisplayName": "Same", "PrimaryEmailAddr": {"Address": "a@x.com"}},
            {"DisplayName": "Same", "PrimaryEmailAddr": {"Address": "b@x.com"}},
            {"DisplayName": "Same", "PrimaryEmailAddr": {"Address": "c@x.com"}},
        ]
        result = deduplicate_display_names(customers)
        self.assertEqual(result[0]["DisplayName"], "Same")
        self.assertEqual(result[1]["DisplayName"], "Same (b@x.com)")
        self.assertEqual(result[2]["DisplayName"], "Same (c@x.com)")


class TestMainCLI(unittest.TestCase):
    def test_end_to_end_file_transform(self):
        shopify_customers = [
            {
                "id": "gid://shopify/Customer/1",
                "firstName": "Alice",
                "lastName": "Wong",
                "email": "alice@example.com",
                "phone": "+1-555-0001",
                "taxExempt": False,
                "tags": ["retail"],
                "defaultAddress": {
                    "address1": "100 First Ave",
                    "city": "Portland",
                    "provinceCode": "OR",
                    "zip": "97201",
                    "countryCodeV2": "US",
                },
            },
            {
                "id": "gid://shopify/Customer/2",
                "firstName": "Bob",
                "lastName": "Lee",
                "email": "bob@example.com",
                "phone": "",
                "taxExempt": True,
                "tags": [],
                "defaultAddress": None,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.json")
            output_path = os.path.join(tmpdir, "output.json")

            with open(input_path, "w") as f:
                json.dump(shopify_customers, f)

            from transform_customers import main as customer_main
            import sys
            old_argv = sys.argv
            sys.argv = ["transform_customers.py", "--input", input_path, "--output", output_path, "--pretty"]
            try:
                customer_main()
            finally:
                sys.argv = old_argv

            with open(output_path) as f:
                output = json.load(f)

            self.assertEqual(output["metadata"]["stats"]["total_input"], 2)
            self.assertEqual(output["metadata"]["stats"]["total_output"], 2)
            self.assertEqual(output["metadata"]["stats"]["tax_exempt_count"], 1)
            self.assertEqual(len(output["customers"]), 2)
            self.assertEqual(output["customers"][0]["DisplayName"], "Alice Wong")
            self.assertFalse(output["customers"][1]["Taxable"])


if __name__ == "__main__":
    unittest.main()
