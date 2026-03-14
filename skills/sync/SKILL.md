---
name: sync
description: >
  Run the Shopify to QuickBooks Online sync pipeline. Extracts customers and orders
  from Shopify via MCP, transforms them using Python scripts with field mapping and
  tax resolution, loads into QBO via MCP, and generates a validation audit report.
  Use when the user says "sync", "export shopify", "import to qbo", "migrate orders",
  "sync customers", "shopify to quickbooks", or asks to move data between the systems.
  This is the main pipeline command.
---

# Shopify -> QBO Sync Pipeline

Execute the four-phase sync pipeline: Extract -> Transform -> Load -> Validate.

## Pre-flight Checks

Before starting, verify both MCP servers are connected:
1. Shopify: list 1 product via Shopify MCP
2. QBO: run `SELECT COUNT(*) FROM Customer` via QBO MCP

If either fails, tell the user to run `/shopify-qbo:configure` or `/shopify-qbo:setup`.

## Phase 1: Extract from Shopify

Pull raw data using Shopify MCP tools:

**Customers:**
```
Tool: get-customers
Params: { "limit": 250 }
```
Paginate if >250. Save to `shopify_customers.json`.

**Orders:**
```
Tool: get-orders
Params: { "limit": 250, "status": "any" }
```
Paginate as needed. Save to `shopify_orders.json`.

Handle arguments:
- `--customers-only`: Skip order extraction
- `--orders-only`: Skip customer extraction
- `--status-filter`: Pass to transform phase (default: "paid")

## Phase 2: Transform

Run the orchestrator script:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py \
  --shopify-customers shopify_customers.json \
  --shopify-orders shopify_orders.json \
  --tax-map ${CLAUDE_PLUGIN_ROOT}/tax-mapping.json \
  --output-dir sync_output \
  --status-filter paid \
  --mode transform-only
```

This produces:
- `sync_output/qbo_customers.json` - QBO-ready customer objects
- `sync_output/qbo_invoices.json` - QBO-ready invoices with tax detail
- `sync_output/sync_audit_*.json` - Pre-load validation report

Review the audit report. If there are issues (orphan invoices, tax discrepancies),
present them to the user before proceeding to Phase 3.

## Phase 3: Load into QBO

If `--dry-run` was specified, stop here and show what would be loaded.

**Customer upsert loop** (for each customer in qbo_customers.json):
1. Query QBO: `SELECT Id, DisplayName, PrimaryEmailAddr FROM Customer WHERE PrimaryEmailAddr = '<email>'`
2. If exists and identical -> skip
3. If exists and changed -> update
4. If not exists -> create via QBO MCP `create_customer`

**Invoice creation loop** (for each invoice in qbo_invoices.json):
1. Query QBO: `SELECT Id, DocNumber FROM Invoice WHERE DocNumber = '<doc_number>'`
2. If exists -> skip (Shopify orders are immutable)
3. If not exists:
   - Resolve CustomerRef by email lookup
   - Create via QBO MCP `create_invoice` (draft mode)
   - Log the created QBO Invoice ID

**Error handling during load:**
- DisplayName collision -> append email in parentheses, retry
- Customer not found for invoice -> create from order billing info, tag as "Shopify Guest"
- Unknown tax code -> default to "TAX", flag in audit
- Single record failure -> log error, continue to next record

**Rate limiting:**
- Shopify: 100ms delay between calls
- QBO: 200ms delay between calls

## Phase 4: Validate

After loading:
1. Sum QBO invoice tax amounts, compare to Shopify totals
2. Flag discrepancies > $0.01
3. Compare created/skipped/error counts against expected totals
4. Generate final `sync_audit_*.json`

Present the audit summary to the user:
- Customers: created / updated / skipped / errored
- Invoices: created / skipped / errored
- Tax: Shopify total vs QBO total, discrepancy
- Action items for manual review

If there are issues, suggest running `/shopify-qbo:reconcile` for deeper analysis.

## Field Mapping Reference

See `${CLAUDE_PLUGIN_ROOT}/references/field-mapping.md` for the complete Shopify -> QBO
field mapping specification.

## Tax Mapping Reference

See `${CLAUDE_PLUGIN_ROOT}/tax-mapping.json` for configurable tax code mappings.
Customizable per jurisdiction (US, CA, GB, AU, EU).
