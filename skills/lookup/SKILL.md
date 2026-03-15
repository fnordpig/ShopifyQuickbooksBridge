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

## Step 5: Generate HTML Comparison View

After presenting the markdown table, generate a self-contained HTML file showing the
two records side-by-side with color-coded match/mismatch fields. Write the file to
`/tmp/shopify-qbo-lookup.html` and open it.

The HTML should include:

- A header with "Shopify ↔ QBO Lookup" branding and the search query
- A two-column comparison card (Shopify on the left, QBO on the right)
- Each field row color-coded:
  - **Green (#28a745)** background for matching fields
  - **Red (#dc3545)** background for mismatched fields
  - **Gray (#6c757d)** background for fields present in only one system
- A summary banner at the top showing total fields, matches, and mismatches
- Self-contained inline CSS, no external dependencies

Style guide:
- Page background: `#f8f9fa`
- Cards: white with `box-shadow: 0 2px 4px rgba(0,0,0,0.1)`
- Font: `system-ui, -apple-system, sans-serif`
- Match/OK rows: light green `#d4edda` with border-left `4px solid #28a745`
- Mismatch rows: light red `#f8d7da` with border-left `4px solid #dc3545`
- Missing rows: light gray `#e9ecef` with border-left `4px solid #6c757d`

```bash
# Claude generates the HTML content inline based on the comparison results
# Write it to file and open it
cat > /tmp/shopify-qbo-lookup.html << 'HTMLEOF'
<!-- Claude generates this dynamically based on actual comparison data -->
HTMLEOF
open /tmp/shopify-qbo-lookup.html
```

The markdown table in chat is still the primary output. The HTML view is an additional
visual aid for the bookkeeper.

## Step 6: Suggest Next Actions

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
