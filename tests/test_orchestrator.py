#!/usr/bin/env python3
"""Tests for orchestrator.py"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from orchestrator import validate_sync, generate_audit_report


def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def _make_customer_output(customers):
    return {"customers": customers}


def _make_invoice_output(invoices):
    return {"invoices": invoices}


class TestValidateSync(unittest.TestCase):
    def _run_validate(self, customers, invoices):
        with tempfile.TemporaryDirectory() as tmpdir:
            cust_path = os.path.join(tmpdir, "customers.json")
            inv_path = os.path.join(tmpdir, "invoices.json")
            _write_json(cust_path, _make_customer_output(customers))
            _write_json(inv_path, _make_invoice_output(invoices))
            return validate_sync(cust_path, inv_path)

    def test_valid_when_all_emails_match(self):
        customers = [
            {"PrimaryEmailAddr": {"Address": "jane@example.com"}, "DisplayName": "Jane"},
        ]
        invoices = [
            {
                "DocNumber": "SH-1001",
                "_customer_email": "jane@example.com",
                "TxnTaxDetail": {"TotalTax": 3.90},
                "_validation": {"shopify_total_tax": "3.90"},
            },
        ]
        result = self._run_validate(customers, invoices)
        self.assertTrue(result["valid"])
        self.assertEqual(result["issues"], [])

    def test_orphan_invoice_detected(self):
        customers = [
            {"PrimaryEmailAddr": {"Address": "alice@example.com"}, "DisplayName": "Alice"},
        ]
        invoices = [
            {
                "DocNumber": "SH-1001",
                "_customer_email": "unknown@example.com",
                "TxnTaxDetail": {"TotalTax": 0},
                "_validation": {"shopify_total_tax": "0"},
            },
        ]
        result = self._run_validate(customers, invoices)
        self.assertFalse(result["valid"])
        issue_types = [i["type"] for i in result["issues"]]
        self.assertIn("orphan_invoices", issue_types)

    def test_duplicate_doc_numbers_detected(self):
        customers = [
            {"PrimaryEmailAddr": {"Address": "a@x.com"}, "DisplayName": "A"},
        ]
        invoices = [
            {
                "DocNumber": "SH-1001",
                "_customer_email": "a@x.com",
                "TxnTaxDetail": {"TotalTax": 0},
                "_validation": {"shopify_total_tax": "0"},
            },
            {
                "DocNumber": "SH-1001",
                "_customer_email": "a@x.com",
                "TxnTaxDetail": {"TotalTax": 0},
                "_validation": {"shopify_total_tax": "0"},
            },
        ]
        result = self._run_validate(customers, invoices)
        self.assertFalse(result["valid"])
        issue_types = [i["type"] for i in result["issues"]]
        self.assertIn("duplicate_doc_numbers", issue_types)

    def test_tax_discrepancy_detected(self):
        customers = [
            {"PrimaryEmailAddr": {"Address": "a@x.com"}, "DisplayName": "A"},
        ]
        invoices = [
            {
                "DocNumber": "SH-1001",
                "_customer_email": "a@x.com",
                "TxnTaxDetail": {"TotalTax": 3.90},
                "_validation": {"shopify_total_tax": "5.00"},  # Mismatch
            },
        ]
        result = self._run_validate(customers, invoices)
        self.assertFalse(result["valid"])
        issue_types = [i["type"] for i in result["issues"]]
        self.assertIn("tax_discrepancy", issue_types)

    def test_small_tax_discrepancy_within_tolerance(self):
        customers = [
            {"PrimaryEmailAddr": {"Address": "a@x.com"}, "DisplayName": "A"},
        ]
        invoices = [
            {
                "DocNumber": "SH-1001",
                "_customer_email": "a@x.com",
                "TxnTaxDetail": {"TotalTax": 3.90},
                "_validation": {"shopify_total_tax": "3.905"},  # Within $0.01
            },
        ]
        result = self._run_validate(customers, invoices)
        tax_issues = [i for i in result["issues"] if i["type"] == "tax_discrepancy"]
        self.assertEqual(len(tax_issues), 0)

    def test_case_insensitive_email_matching(self):
        customers = [
            {"PrimaryEmailAddr": {"Address": "Jane@Example.com"}, "DisplayName": "Jane"},
        ]
        invoices = [
            {
                "DocNumber": "SH-1001",
                "_customer_email": "jane@example.com",
                "TxnTaxDetail": {"TotalTax": 0},
                "_validation": {"shopify_total_tax": "0"},
            },
        ]
        result = self._run_validate(customers, invoices)
        orphan_issues = [i for i in result["issues"] if i["type"] == "orphan_invoices"]
        self.assertEqual(len(orphan_issues), 0)

    def test_summary_counts(self):
        customers = [
            {"PrimaryEmailAddr": {"Address": "a@x.com"}, "DisplayName": "A"},
            {"PrimaryEmailAddr": {"Address": "b@x.com"}, "DisplayName": "B"},
        ]
        invoices = [
            {
                "DocNumber": "SH-1",
                "_customer_email": "a@x.com",
                "TxnTaxDetail": {"TotalTax": 1.0},
                "_validation": {"shopify_total_tax": "1.0"},
            },
            {
                "DocNumber": "SH-2",
                "_customer_email": "b@x.com",
                "TxnTaxDetail": {"TotalTax": 2.0},
                "_validation": {"shopify_total_tax": "2.0"},
            },
        ]
        result = self._run_validate(customers, invoices)
        self.assertEqual(result["summary"]["customers"], 2)
        self.assertEqual(result["summary"]["invoices"], 2)
        self.assertEqual(result["summary"]["total_tax_mapped"], 3.0)

    def test_empty_inputs(self):
        result = self._run_validate([], [])
        self.assertTrue(result["valid"])
        self.assertEqual(result["summary"]["customers"], 0)
        self.assertEqual(result["summary"]["invoices"], 0)


class TestGenerateAuditReport(unittest.TestCase):
    def test_generates_report_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            customer_stats = {"total_input": 2, "total_output": 2}
            invoice_stats = {"total_input": 3, "total_output": 3}
            validation = {"valid": True, "issues": [], "summary": {}}

            report_path = generate_audit_report(
                customer_stats, invoice_stats, validation, tmpdir
            )

            self.assertTrue(os.path.exists(report_path))
            self.assertIn("sync_audit_", report_path)

            with open(report_path) as f:
                report = json.load(f)

            self.assertEqual(report["report_type"], "shopify_qbo_sync_audit")
            self.assertIn("generated_at", report)
            self.assertEqual(report["phases"]["transform"]["customers"], customer_stats)
            self.assertEqual(report["phases"]["transform"]["invoices"], invoice_stats)

    def test_no_issues_gives_ready_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validation = {"valid": True, "issues": [], "summary": {}}
            report_path = generate_audit_report({}, {}, validation, tmpdir)

            with open(report_path) as f:
                report = json.load(f)

            self.assertEqual(len(report["action_items"]), 1)
            self.assertIn("ready for QBO import", report["action_items"][0])

    def test_orphan_invoice_action_item(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validation = {
                "valid": False,
                "issues": [{"type": "orphan_invoices", "count": 3, "details": []}],
                "summary": {},
            }
            report_path = generate_audit_report({}, {}, validation, tmpdir)

            with open(report_path) as f:
                report = json.load(f)

            self.assertTrue(any("3 invoices" in item for item in report["action_items"]))

    def test_duplicate_doc_number_action_item(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validation = {
                "valid": False,
                "issues": [{"type": "duplicate_doc_numbers", "count": 2, "details": ["SH-1001"]}],
                "summary": {},
            }
            report_path = generate_audit_report({}, {}, validation, tmpdir)

            with open(report_path) as f:
                report = json.load(f)

            self.assertTrue(any("duplicate" in item.lower() for item in report["action_items"]))

    def test_tax_discrepancy_action_item(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validation = {
                "valid": False,
                "issues": [{"type": "tax_discrepancy", "discrepancy": 1.10, "qbo_total_tax": 5.0, "shopify_total_tax": 3.9}],
                "summary": {},
            }
            report_path = generate_audit_report({}, {}, validation, tmpdir)

            with open(report_path) as f:
                report = json.load(f)

            self.assertTrue(any("$1.10" in item for item in report["action_items"]))

    def test_load_phase_status_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validation = {"valid": True, "issues": [], "summary": {}}
            report_path = generate_audit_report({}, {}, validation, tmpdir)

            with open(report_path) as f:
                report = json.load(f)

            self.assertEqual(report["phases"]["load"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
