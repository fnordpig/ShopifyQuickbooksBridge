---
name: fix
description: >
  Investigate and propose corrections for data discrepancies between Shopify and
  QuickBooks Online. Fixes tax codes, amounts, customer references, line items,
  and stale customer data. Uses a propose-then-confirm pattern — never writes
  without user approval. Use when the user says "fix", "correct", "wrong tax",
  "update invoice", "mismatch", "discrepancy", or reports that data looks wrong.
---

# Fix Discrepancies

Investigate a record, show what's wrong, propose a fix, and apply it after
confirmation.

## What This Command Fixes

- Tax code or tax amount mismatches
- Incorrect line item amounts or quantities
- Wrong or stale CustomerRef on invoices
- Outdated customer data (name, email, phone, address)
- Missing or incorrect PrivateNote provenance tags

## What This Command Does NOT Fix

- Records where amounts already match (nothing to fix)
- Finalized/paid invoices in QBO (cannot edit; suggest credit memo)
- Customer merges (refer to `/shopify-qbo:resolve-customers`)

## Step 1: Identify the Record

Parse the user's input to determine the target:
- Order number (`#1042`, `SH-1042`) -> look up Invoice by DocNumber
- Invoice number (`Inv-1042`) -> look up Invoice by DocNumber
- Customer name or email -> look up Customer by DisplayName or email
- Description of the issue -> search both systems for matching records

## Step 2: Fetch from Both Systems

**Invoice fix:**

Shopify MCP:
```
get-order by order number (extract from DocNumber by stripping "SH-" prefix)
```

QBO MCP:
```
SELECT * FROM Invoice WHERE DocNumber = 'SH-<order_number>'
```

**Customer fix:**

Shopify MCP:
```
get-customers with query matching name or email
```

QBO MCP:
```
SELECT * FROM Customer WHERE DisplayName LIKE '%<name>%'
  OR PrimaryEmailAddr = '<email>'
```

## Step 3: Diff the Records

Run the diff script to identify discrepancies:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/diff_records.py \
  --shopify-record '<shopify_json>' \
  --qbo-record '<qbo_json>' \
  --record-type invoice|customer
```

The script outputs a structured diff with field-level comparisons.

## Step 4: Present Discrepancies

Show a clear table of what's wrong:

| Field | Shopify (source of truth) | QBO (current) | Action |
|-------|--------------------------|---------------|--------|
| Tax Code | HST (13%) | TAX (default) | Update to HST |
| Tax Amount | $12.38 | $12.37 | Update to $12.38 |
| Phone | 555-0100 | (empty) | Add phone |
| Email | jane@new.com | jane@old.com | Update email |

If no discrepancies are found, tell the user: "Records are already in sync —
no fixes needed."

## Step 5: Propose Fix (Require Confirmation)

Present the proposed changes in plain English:

> **Proposed fix for Invoice SH-1042:**
> 1. Update TxnTaxDetail.TaxLine[0].TaxRateRef from "TAX" to "HST"
> 2. Update TxnTaxDetail.TotalTax from $12.37 to $12.38
>
> This will modify 1 invoice in QuickBooks Online.
>
> **Proceed? (yes/no)**

**Do NOT execute any writes until the user confirms.**

## Step 6: Execute the Fix

After confirmation, apply changes via QBO MCP:

**For invoices:**
Use the QBO MCP update tool with the corrected fields. Include the full
SyncToken from the fetched record to prevent conflicts.

**For customers:**
Use the QBO MCP update tool with the corrected fields.

**In both cases, update the PrivateNote:**
Append a fix log entry:
```
[shopify-qbo:fix] Updated <field1>, <field2> on <date>
```

Preserve any existing `[shopify-sync:gid]` tag in the PrivateNote.

## Step 7: Verify and Report

After the update, re-fetch the QBO record and confirm the fix was applied:

| Field | Before | After | Status |
|-------|--------|-------|--------|
| Tax Code | TAX | HST | ✓ Fixed |
| Tax Amount | $12.37 | $12.38 | ✓ Fixed |

If the update fails (e.g., stale SyncToken), re-fetch and retry once. If it
fails again, report the error and suggest the user check QBO directly.

## Error Handling

| Error | Action |
|-------|--------|
| Record not found in QBO | Suggest running `/shopify-qbo:sync` first |
| Record not found in Shopify | May be a QBO-only record; show QBO data and ask user what to do |
| Invoice is paid/finalized | Cannot edit; suggest voiding and re-creating, or creating a credit memo |
| SyncToken conflict | Re-fetch record and retry |
| Multiple matches | Present all matches and ask user to pick one |
