---
name: lookup
description: >
  Cross-system customer and order search across Shopify and QuickBooks Online.
  Finds records by name, email, order number, or date range and presents a
  side-by-side comparison with suggested next actions. Use when the user says
  "find customer", "look up order", "search for", "where is", "show me customer X",
  "find order", or asks to locate any record across the two systems.
---

# Cross-System Lookup

Search for customers or orders across both Shopify and QBO, then present a
unified side-by-side view.

## Step 1: Parse the Query

Determine what the user is searching for:

| Input pattern | Search type | Example |
|---------------|-------------|---------|
| Email address | Customer by email | `jane@example.com` |
| Name (first last) | Customer by name | `Jane Doe` |
| `#1234` or `SH-1234` | Order/invoice by number | `#1042` |
| Date or date range | Orders by date | `last week`, `2026-03-01 to 2026-03-14` |

## Step 2: Fetch from Both Systems

**Customer search:**

Shopify MCP:
```
get-customers with query matching the name or email
```

QBO MCP:
```
SELECT Id, DisplayName, PrimaryEmailAddr, Balance, PrivateNote
FROM Customer
WHERE DisplayName LIKE '%<name>%'
   OR PrimaryEmailAddr = '<email>'
```

**Order/invoice search:**

Shopify MCP:
```
get-orders with query matching the order number or date range
```

QBO MCP:
```
SELECT Id, DocNumber, TotalAmt, Balance, TxnDate, CustomerRef, PrivateNote
FROM Invoice
WHERE DocNumber = 'SH-<order_number>'
```

For date range queries, use `TxnDate` filters on QBO and created_at on Shopify.

## Step 3: Process Results

Run the lookup script to normalize and align records:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lookup_records.py \
  --shopify-data '<shopify_json>' \
  --qbo-data '<qbo_json>' \
  --search-type customer|order
```

The script outputs a structured comparison with match status and field diffs.

## Step 4: Present Side-by-Side Table

**For customers:**

| Field | Shopify | QBO | Match |
|-------|---------|-----|-------|
| Name | Jane Doe | Jane Doe | ✓ |
| Email | jane@example.com | jane@example.com | ✓ |
| Phone | 555-0100 | (missing) | ✗ |
| Address | 123 Main St | 123 Main St | ✓ |
| Shopify GID | gid://shopify/Customer/123 | [shopify-sync:gid://shopify/Customer/123] | ✓ |

**For orders/invoices:**

| Field | Shopify Order | QBO Invoice | Match |
|-------|--------------|-------------|-------|
| Number | #1042 | SH-1042 | ✓ |
| Date | 2026-03-10 | 2026-03-10 | ✓ |
| Subtotal | $150.00 | $150.00 | ✓ |
| Tax | $12.38 | $12.37 | ✗ |
| Total | $162.38 | $162.37 | ✗ |
| Customer | Jane Doe | Jane Doe | ✓ |
| Line items | 3 | 3 | ✓ |

## Step 5: Suggest Next Actions

Based on the results, suggest relevant commands:

| Situation | Suggestion |
|-----------|------------|
| Record found in Shopify but not QBO | "Run `/shopify-qbo:sync` to import this record" |
| Data mismatch between systems | "Run `/shopify-qbo:fix <record>` to correct the discrepancy" |
| Duplicate customers found | "Run `/shopify-qbo:resolve-customers <name>` to merge or clean up" |
| Record found in QBO but not Shopify | "This may be a QBO-only record — run `/shopify-qbo:resolve-customers` to review" |
| No record found in either system | "No matching records found. Check the spelling or try a broader search." |
| Everything matches | "Records are in sync — no action needed." |

## No Results Handling

If no records are found in either system, clearly state that and suggest:
- Double-check spelling or try alternate names/emails
- Widen the date range
- Search by a different field (email instead of name, or vice versa)
