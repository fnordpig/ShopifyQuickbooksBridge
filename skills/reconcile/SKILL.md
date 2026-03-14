---
name: reconcile
description: >
  Tax reconciliation and audit between Shopify and QuickBooks Online.
  Compares tax totals, validates field mappings, flags discrepancies, and generates
  detailed audit reports with action items. Use when the user says "reconcile",
  "check taxes", "audit sync", "compare totals", "validate tax mapping",
  "review discrepancies", or wants to verify data integrity after a sync.
---

# Tax Reconciliation & Audit

Compare Shopify and QBO data to identify and resolve discrepancies.

## Quick Reconciliation

For a quick check after a sync, read the most recent audit report:

```bash
ls -t sync_output/sync_audit_*.json | head -1
```

Review the `validate` section for issues.

## Deep Reconciliation

### Step 1: Pull Current QBO State

Query QBO for all synced invoices:
```
SELECT Id, DocNumber, TotalAmt, TxnTaxDetail FROM Invoice WHERE DocNumber LIKE 'SH-%'
```

### Step 2: Pull Matching Shopify Orders

For each QBO invoice, extract the order number from DocNumber (strip "SH-" prefix)
and fetch the corresponding Shopify order via MCP.

### Step 3: Compare

For each order/invoice pair:
- Compare line item counts
- Compare subtotals
- Compare tax amounts (tolerance: $0.01)
- Compare customer references

### Step 4: Generate Report

Run the orchestrator's validation:
```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py \
  --shopify-customers shopify_customers.json \
  --shopify-orders shopify_orders.json \
  --tax-map ${CLAUDE_PLUGIN_ROOT}/tax-mapping.json \
  --output-dir sync_output \
  --mode transform-only
```

Review the audit report's `validate.summary` section:
- `total_tax_mapped` vs `total_shopify_tax_original`
- `tax_discrepancy` (should be $0.00)
- `orphan_invoice_count` (should be 0)

### Step 5: QBO Financial Reports

For broader validation, pull QBO reports:

**Profit & Loss:**
Use QBO MCP `profit_and_loss` tool with the relevant date range.

**Tax Summary:**
Query: `SELECT Id, Name, RateValue FROM TaxRate`

Compare QBO tax rates against `tax-mapping.json` to ensure mappings are correct.

## Common Discrepancy Causes

| Issue | Cause | Fix |
|-------|-------|-----|
| Tax total mismatch | Rounding differences between Shopify decimals and QBO percentages | Usually < $0.01, acceptable |
| Missing invoices | Orders filtered by status during transform | Re-run with `--status-filter all` |
| Wrong tax code | Unmapped Shopify tax title defaulted to "TAX" | Add mapping to `tax-mapping.json` |
| Orphan invoices | Customer in order not in customer export | Customer may already exist in QBO, or is a guest checkout |
| Duplicate DocNumber | Same order synced twice | Delete duplicate in QBO, investigate trigger |

## Tax Mapping Audit

To verify tax mappings are correct for the user's jurisdiction:

1. Query Shopify for unique tax titles across all orders
2. Query QBO for available TaxRate entities
3. Compare against `tax-mapping.json`
4. Flag any Shopify tax titles not explicitly mapped (using defaults)
5. Suggest additions to `tax-mapping.json`
