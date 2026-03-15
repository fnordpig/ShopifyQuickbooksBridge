---
name: undo
description: >
  Reverse recent sync or fix actions by tracing PrivateNote provenance tags in
  QuickBooks Online. Finds records created or modified by the pipeline and
  proposes reversal. Use when the user says "undo", "revert", "rollback",
  "take back", "reverse", "undo last sync", or wants to back out a recent change.
---

# Undo Recent Actions

Reverse recent actions performed by the sync pipeline or fix command by tracing
PrivateNote provenance tags.

## What Can Be Undone

| Action | Undo method |
|--------|-------------|
| Customer created by sync | Delete or inactivate the QBO customer |
| Invoice created by sync | Delete the QBO invoice (if no payments linked) |
| Field updated by fix | Revert to previous value (if logged in PrivateNote) |
| Customer inactivated by delete | Re-activate the customer |

## What CANNOT Be Undone

| Action | Why | Alternative |
|--------|-----|-------------|
| Deleted records | Record is gone from QBO | Re-run `/shopify-qbo:sync` to re-import |
| Finalized/paid invoices | QBO prevents editing | Void in QBO UI and re-sync |
| Shopify changes | This tool only modifies QBO | Manual fix in Shopify admin |

If the user asks to undo something that cannot be undone, explain why and
suggest the alternative.

## Step 1: Parse the Description

Interpret what the user wants to undo:
- "undo last sync" -> find all records with recent `[shopify-sync:*]` tags
- "undo fix on SH-1042" -> find invoice SH-1042, check for `[shopify-qbo:fix]` tag
- "revert customer Jane Doe" -> find customer, check for modification tags
- "undo everything from today" -> find all records tagged with today's date

## Step 2: Find Undo Targets

Fetch QBO records that match the description:

```
SELECT Id, DocNumber, TotalAmt, CustomerRef, PrivateNote, MetaData
FROM Invoice
WHERE PrivateNote LIKE '%shopify-sync%' OR PrivateNote LIKE '%shopify-qbo:%'
```

```
SELECT Id, DisplayName, PrimaryEmailAddr, PrivateNote, MetaData
FROM Customer
WHERE PrivateNote LIKE '%shopify-sync%' OR PrivateNote LIKE '%shopify-qbo:%'
```

Run the undo target finder:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/find_undo_targets.py \
  --qbo-invoices '<invoices_json>' \
  --qbo-customers '<customers_json>' \
  --description '<user_description>' \
  --date-filter '<date_if_applicable>'
```

The script parses PrivateNote tags and MetaData timestamps to identify which
records match the user's undo request. It returns a structured list of targets
with proposed reversal actions.

## Step 3: Present the Reversal Plan

Show what will be reversed:

> **Reversal plan for "undo last sync":**
>
> | # | Type | Record | Created/Modified | Proposed Action |
> |---|------|--------|-----------------|-----------------|
> | 1 | Invoice | SH-1042 ($162.38) | 2026-03-14 | Delete |
> | 2 | Invoice | SH-1041 ($89.99) | 2026-03-14 | Delete |
> | 3 | Customer | Jane Doe | 2026-03-14 | Inactivate |
> | 4 | Customer | Bob Smith | 2026-03-14 | Inactivate |
>
> **Total: 2 invoices to delete, 2 customers to inactivate.**
>
> **Proceed? (yes/no)**

For fix reversals, show the field-level changes:

> **Reversal plan for "undo fix on SH-1042":**
>
> | Field | Current (after fix) | Revert to | Source |
> |-------|-------------------|-----------|--------|
> | Tax Code | HST | TAX | PrivateNote log |
> | Tax Amount | $12.38 | $12.37 | PrivateNote log |
>
> **Proceed? (yes/no)**

**Do NOT execute any changes until the user confirms.**

## Step 4: Execute the Reversal

After confirmation, process each target:

**Delete invoices:**
1. Check for linked payments first (same safety check as delete command)
2. If payments exist, skip and report: "Cannot delete SH-1042 — has linked payment"
3. If safe, delete via QBO MCP

**Inactivate customers:**
1. Set `Active: false` via QBO MCP update
2. Update PrivateNote: `[shopify-qbo:undo] Inactivated (undo of sync) on <date>`

**Revert field changes:**
1. Update the fields to their previous values via QBO MCP
2. Update PrivateNote: `[shopify-qbo:undo] Reverted <field1>, <field2> on <date>`

## Step 5: Report Results

Present a completion summary:

| # | Record | Action | Status |
|---|--------|--------|--------|
| 1 | Invoice SH-1042 | Delete | ✓ Done |
| 2 | Invoice SH-1041 | Delete | ✓ Done |
| 3 | Customer Jane Doe | Inactivate | ✓ Done |
| 4 | Customer Bob Smith | Inactivate | ✗ Has linked invoices — skipped |

If any actions were skipped, explain why and suggest alternatives.

Remind the user: "To re-import these records from Shopify, run
`/shopify-qbo:sync`."

## Error Handling

| Error | Action |
|-------|--------|
| No matching records found | "No records match that description. Check the wording or try a broader search." |
| Record already deleted | "Record is already gone from QBO. Nothing to undo." |
| Invoice has payments | Skip; report to user and suggest voiding in QBO UI |
| PrivateNote has no fix log | "Cannot determine previous values — no fix history in PrivateNote." |
| SyncToken conflict | Re-fetch and retry once |
