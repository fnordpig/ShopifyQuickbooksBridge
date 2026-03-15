---
name: report
description: >
  Generate rich reports on sync status, financials, reconciliation, or taxes.
  Four report types: sync-status (default), financial, reconciliation, and tax.
  All accept optional date ranges and can produce HTML artifact output.
  Use when the user says "report", "show me", "how many synced", "P&L",
  "profit and loss", "balance sheet", "tax summary", "give me a summary",
  or asks for any kind of data overview.
---

# Reports

Generate and present data reports with rich markdown tables and optional HTML
artifact output.

## Report Types

| Type | Description | Default? |
|------|-------------|----------|
| `sync-status` | Overview of synced records, counts, and health | Yes (no args) |
| `financial` | P&L, revenue, and balance data from QBO | No |
| `reconciliation` | Side-by-side Shopify vs QBO totals with discrepancies | No |
| `tax` | Tax collection summary by jurisdiction and rate | No |

All reports accept `--date-range START END` (defaults to current month).

## Step 1: Determine Report Type

Parse the user's input:
- No arguments or "sync status" or "summary" -> `sync-status`
- "P&L", "profit and loss", "revenue", "balance sheet", "financial" -> `financial`
- "reconciliation", "compare", "discrepancies" -> `reconciliation`
- "tax", "tax summary", "tax report", "HST", "GST", "sales tax" -> `tax`

Parse date range if provided; default to first and last day of current month.

## Step 2: Fetch Data via MCP

### sync-status
QBO MCP:
```
SELECT COUNT(*) FROM Customer WHERE PrivateNote LIKE '%shopify-sync%'
SELECT COUNT(*) FROM Invoice WHERE DocNumber LIKE 'SH-%'
SELECT Id, DocNumber, TotalAmt, Balance, TxnDate FROM Invoice
  WHERE DocNumber LIKE 'SH-%' ORDER BY TxnDate DESC MAXRESULTS 10
```

Shopify MCP:
```
get-customers count
get-orders count
```

### financial
QBO MCP:
```
profit_and_loss for the date range
balance_sheet as of end date
```

### reconciliation
Fetch all synced invoices from QBO and matching orders from Shopify (same as
the reconcile skill, but summarized for reporting).

### tax
QBO MCP:
```
SELECT Id, Name, RateValue FROM TaxRate
SELECT TxnTaxDetail FROM Invoice WHERE DocNumber LIKE 'SH-%'
  AND TxnDate >= '<start>' AND TxnDate <= '<end>'
```

Shopify MCP:
```
get-orders with date range, extract tax_lines
```

## Step 3: Generate the Report

Run the report generator:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/generate_report.py \
  --type sync-status|financial|reconciliation|tax \
  --shopify-data '<shopify_json>' \
  --qbo-data '<qbo_json>' \
  --date-range '<start>' '<end>' \
  --html-output report.html
```

The `--html-output` flag is optional; include it when the user requests an
HTML artifact or when the data is complex enough to benefit from visual
presentation.

## Step 4: Present as Rich Markdown

### sync-status Report

```
Sync Status Report — March 2026
================================

Customers:  42 in Shopify | 40 in QBO | 2 missing
Invoices:  128 in Shopify | 125 in QBO | 3 missing
Last sync:  2026-03-14 03:00:29 UTC
```

| Metric | Shopify | QBO | Status |
|--------|---------|-----|--------|
| Customers | 42 | 40 | ✗ 2 missing |
| Orders/Invoices | 128 | 125 | ✗ 3 missing |
| Total Revenue | $15,234.56 | $15,234.56 | ✓ Match |
| Total Tax | $1,980.49 | $1,980.48 | ✗ $0.01 rounding |

**Recent synced invoices:**

| DocNumber | Date | Amount | Customer | Status |
|-----------|------|--------|----------|--------|
| SH-1042 | 2026-03-14 | $162.38 | Jane Doe | ✓ Synced |
| SH-1041 | 2026-03-13 | $89.99 | Bob Smith | ✓ Synced |

### financial Report

Present P&L and balance sheet data in clean tables. Include totals and
period-over-period comparison if prior period data is available.

### reconciliation Report

| Order # | Shopify Total | QBO Total | Difference | Status |
|---------|--------------|-----------|------------|--------|
| 1042 | $162.38 | $162.38 | $0.00 | ✓ |
| 1041 | $89.99 | $89.98 | $0.01 | ✗ Rounding |
| 1039 | $245.00 | — | — | ✗ Missing from QBO |

### tax Report

| Jurisdiction | Tax Rate | Shopify Collected | QBO Recorded | Difference |
|-------------|----------|-------------------|-------------|------------|
| ON (HST) | 13% | $1,234.56 | $1,234.56 | $0.00 ✓ |
| BC (GST+PST) | 12% | $456.78 | $456.77 | $0.01 ✗ |
| AB (GST) | 5% | $289.15 | $289.15 | $0.00 ✓ |

## Step 5: Offer HTML Artifact

After presenting the markdown report, offer:

> An HTML version of this report has been saved to `report.html`. You can open
> it in a browser for a formatted, printable view.

If the user didn't request HTML, still mention the option:

> Want an HTML version of this report? Just ask and I'll generate one.

## Error Handling

| Error | Action |
|-------|--------|
| No synced data found | "No synced records found. Run `/shopify-qbo:sync` first." |
| MCP connection failed | "Cannot reach QBO/Shopify. Run `/shopify-qbo:status` to diagnose." |
| Invalid date range | "Could not parse date range. Use format: YYYY-MM-DD YYYY-MM-DD" |
| Empty report | Present the report structure with zeros and note no data in range |
