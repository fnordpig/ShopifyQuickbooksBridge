---
description: "Run the Shopify -> QBO sync pipeline. Extracts customers and orders from Shopify, transforms them to QBO format, loads into QuickBooks, and generates an audit report."
argument-hint: "[--customers-only] [--orders-only] [--dry-run] [--status-filter paid|all]"
---

Use the `shopify-qbo:sync` skill to run the four-phase sync pipeline.
