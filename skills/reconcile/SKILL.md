---
name: reconcile
description: >
  Deep record-by-record consistency check between Shopify and QuickBooks Online.
  Compares every synced order field-by-field, identifies missing records, orphaned
  invoices, and data mismatches. Offers to batch-fix issues. Use when the user says
  "reconcile", "audit sync", "check consistency", "validate data", "compare records",
  "verify sync", or wants a thorough integrity check between the systems.
  Distinct from /shopify-qbo:report reconciliation which only compares totals.
---

# Deep Record-by-Record Reconciliation

Walk every synced record and compare field-by-field between Shopify and QBO.

## Step 1: Pull All Synced Records

**QBO invoices:**
```
SELECT Id, DocNumber, TxnDate, TotalAmt, Balance, CustomerRef, TxnTaxDetail, Line, PrivateNote
FROM Invoice WHERE DocNumber LIKE 'SH-%'
```

**QBO customers (synced):**
```
SELECT Id, DisplayName, PrimaryEmailAddr, GivenName, FamilyName, PrimaryPhone, BillAddr, Notes, PrivateNote
FROM Customer WHERE PrivateNote LIKE '%shopify-sync%'
```

**Shopify orders:**
Use `get-orders` with pagination to fetch all orders.

**Shopify customers:**
Use `get-customers` with pagination to fetch all customers.

Save all raw data to temp JSON files.

## Step 2: Run Diff Script on Each Pair

For each QBO invoice with DocNumber `SH-{number}`, find the matching Shopify order
by order number. For each pair, run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/diff_records.py \
  --type invoice \
  --shopify /tmp/shopify_order_{number}.json \
  --qbo /tmp/qbo_invoice_{number}.json \
  --tax-map ${CLAUDE_PLUGIN_ROOT}/tax-mapping.json
```

Collect all results. Also identify:
- **Shopify orders missing from QBO** — orders with no matching `SH-{number}` invoice
- **Orphaned QBO invoices** — invoices with `[shopify-sync]` PrivateNote but no matching Shopify order

## Step 3: Present Summary

```
Reconciliation — March 2026: 140 invoices checked

✓ 136 fully consistent
✗ 4 with issues:

  #1042  Tax: Shopify 6.5% ($7.80) vs QBO 0% ($0.00)
  #1087  Missing from QBO entirely
  #1103  Customer: Shopify "Jane Smith" vs QBO "J. Smith"
  #1118  Line item count: Shopify 3 items vs QBO 2 items

Fix all 4? (Each will be proposed individually for confirmation)
```

## Step 4: Generate HTML Reconciliation Dashboard

After presenting the markdown summary, generate a self-contained HTML dashboard.
Write the file to `/tmp/shopify-qbo-reconcile.html` and open it.

The HTML should include:

- A header with "Shopify ↔ QBO Reconciliation" branding and the date range
- A summary banner showing:
  - Total records checked
  - Count of fully consistent records (green badge)
  - Count of records with issues (red badge)
  - Percentage consistent
- A full table of all reconciled records:
  - **Green (#28a745)** row background (`#d4edda`) for consistent records
  - **Red (#dc3545)** row background (`#f8d7da`) for records with issues
- Issue rows are expandable (use HTML `<details>/<summary>`) to reveal field-level
  detail showing which specific fields differ and their Shopify vs QBO values
- A separate section for missing records (Shopify orders not in QBO) and orphaned
  records (QBO invoices not in Shopify)
- Self-contained inline CSS and vanilla JS for expand/collapse, no external dependencies

Style guide:
- Page background: `#f8f9fa`
- Cards: white with `box-shadow: 0 2px 4px rgba(0,0,0,0.1)`
- Font: `system-ui, -apple-system, sans-serif`
- Consistent rows: `background: #d4edda` with left border `4px solid #28a745`
- Issue rows: `background: #f8d7da` with left border `4px solid #dc3545`
- Missing records: `background: #fff3cd` with left border `4px solid #ffc107`
- Orphaned records: `background: #e9ecef` with left border `4px solid #6c757d`
- Summary banner: large font with pill-shaped count badges

```bash
# Claude generates the HTML content inline based on the reconciliation results
cat > /tmp/shopify-qbo-reconcile.html << 'HTMLEOF'
<!-- Claude generates this dynamically based on actual reconciliation data -->
HTMLEOF
open /tmp/shopify-qbo-reconcile.html
```

The markdown summary in chat is still the primary output. The HTML dashboard gives
the bookkeeper an interactive, detailed view of all reconciliation results.

## Step 5: Batch Fix (Optional)

If the user wants to fix issues:
1. Process each issue one at a time using the same flow as `/shopify-qbo:fix`
2. For missing records, suggest running `/shopify-qbo:sync`
3. For orphaned records, suggest `/shopify-qbo:delete`
4. For data mismatches, propose the specific correction
5. **Confirm each fix individually** before executing

## Common Discrepancy Causes

| Issue | Cause | Fix |
|-------|-------|-----|
| Tax total mismatch | Rounding between Shopify decimals and QBO percentages | Usually < $0.01, acceptable |
| Missing invoices | Orders filtered by status during transform | Re-run sync with `--status-filter all` |
| Wrong tax code | Unmapped Shopify tax title defaulted to "TAX" | Add mapping to `tax-mapping.json` |
| Orphan invoices | Shopify order deleted or customer removed | Review and delete from QBO if appropriate |
| Duplicate DocNumber | Same order synced twice | Delete duplicate via `/shopify-qbo:delete` |
| Customer name drift | Customer updated in Shopify after sync | Fix via `/shopify-qbo:resolve-customers` |

## Tax Mapping Audit

To verify tax mappings are correct for the user's jurisdiction:

1. Query Shopify for unique tax titles across all orders
2. Query QBO: `SELECT Id, Name, RateValue FROM TaxRate`
3. Compare against `${CLAUDE_PLUGIN_ROOT}/tax-mapping.json`
4. Flag any Shopify tax titles not explicitly mapped (using defaults)
5. Suggest additions to `tax-mapping.json`
