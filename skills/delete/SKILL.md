---
name: delete
description: >
  Guided deletion of QBO records with safety checks. Verifies no linked payments
  exist before deleting invoices, and prefers inactivation over deletion for
  customers. Uses a propose-then-confirm pattern. Use when the user says "delete",
  "remove", "void", "get rid of", "duplicate invoice", or wants to remove a
  record from QuickBooks Online.
---

# Guided Record Deletion

Safely delete or inactivate QBO records with pre-deletion safety checks.

## Safety Rules

1. **REFUSE to delete invoices with linked payments.** If a payment is applied,
   tell the user to void the invoice in the QBO web UI instead.
2. **Prefer inactivation for customers.** Deleting a customer removes history.
   Always suggest marking as inactive first; only delete if the user insists
   and there are no linked transactions.
3. **Never delete Shopify records.** This command only operates on QBO.
4. **Always require explicit confirmation before any destructive action.**

## Step 1: Identify the Record

Parse the user's input to determine the target:
- Invoice number (`SH-1042`, `Inv-1042`) -> Invoice by DocNumber
- Customer name or email -> Customer by DisplayName or email
- Description ("that duplicate invoice for Jane") -> search by context

## Step 2: Fetch the Record and Run Safety Checks

**For invoices:**

QBO MCP:
```
SELECT Id, DocNumber, TotalAmt, Balance, CustomerRef, SyncToken, PrivateNote
FROM Invoice
WHERE DocNumber = 'SH-<number>'
```

Then check for linked payments:
```
SELECT Id, TotalAmt, TxnDate FROM Payment
WHERE Line.LinkedTxn.TxnId = '<invoice_id>'
```

**For customers:**

QBO MCP:
```
SELECT Id, DisplayName, PrimaryEmailAddr, Balance, Active, SyncToken, PrivateNote
FROM Customer
WHERE DisplayName LIKE '%<name>%'
```

Then check for linked transactions:
```
SELECT COUNT(*) FROM Invoice WHERE CustomerRef = '<customer_id>'
```

## Step 3: Evaluate Safety Check Results

**Invoice with linked payments:**
```
Cannot delete Invoice SH-1042 — it has a linked payment of $162.38
from 2026-03-12.

To remove this invoice, void it in the QuickBooks Online web UI:
  1. Go to Sales > Invoices
  2. Find SH-1042
  3. Click More > Void

After voiding, you can re-sync from Shopify if needed with
`/shopify-qbo:sync`.
```

**STOP here — do not proceed with deletion.**

**Customer with linked invoices:**
```
Customer "Jane Doe" has 5 linked invoices in QBO.

Recommended: Mark as inactive instead of deleting (preserves history).
If you still want to delete, you must first delete or reassign all
linked invoices.

Proceed with inactivation? (yes/no)
```

## Step 4: Present What Will Be Deleted

**Visual confirmation:** Since deletion is destructive, present the confirmation
in a clear, visually distinct way in chat. Use **bold** for the record details,
indent the summary as a blockquote, and end with a prominent **YES/NO** prompt.
No HTML artifact is needed for this simple confirm/execute flow.

If safety checks pass, present a clear summary:

> **Proposed deletion:**
>
> | Record | Details |
> |--------|---------|
> | Type | Invoice |
> | DocNumber | SH-1042 |
> | Amount | $162.38 |
> | Customer | Jane Doe |
> | Created | 2026-03-10 |
> | Provenance | [shopify-sync:gid://shopify/Order/123456] |
>
> **This action cannot be undone.** The record will be permanently removed
> from QuickBooks Online.
>
> **Proceed? (yes/no)**

**Do NOT execute any deletes until the user confirms.**

## Step 5: Execute the Deletion

After confirmation:

**For invoices:**
Use QBO MCP delete tool with the Invoice Id and SyncToken.

**For customers (inactivation):**
Use QBO MCP update tool to set `Active: false` on the Customer record.

**For customers (full delete, only if user insists and no linked transactions):**
Use QBO MCP delete tool with the Customer Id and SyncToken.

## Step 6: Log to PrivateNote

For inactivated customers, update the PrivateNote:
```
[shopify-qbo:delete] Inactivated on <date>
```

For deleted records, there is no record to update, but log the action to the
console output so the user has a record:

```
Deleted Invoice SH-1042 (QBO Id: 456, was linked to Shopify order
gid://shopify/Order/123456) on 2026-03-14.
```

## Step 7: Confirm Completion

After deletion, verify the record is gone:

```
SELECT Id FROM Invoice WHERE DocNumber = 'SH-1042'
```

Report the result:

| Action | Record | Status |
|--------|--------|--------|
| Delete | Invoice SH-1042 | ✓ Removed |

Or for inactivation:

| Action | Record | Status |
|--------|--------|--------|
| Inactivate | Customer Jane Doe | ✓ Marked inactive |

Remind the user: "Deleted records cannot be recovered. If this was a synced
Shopify record, run `/shopify-qbo:sync` to re-import it."

## Error Handling

| Error | Action |
|-------|--------|
| Record not found | "No record matching that description was found in QBO." |
| Multiple matches | Present all matches and ask user to pick one |
| SyncToken conflict | Re-fetch and retry once |
| Linked payments | REFUSE deletion; suggest voiding in QBO UI |
| API error | Report the error and suggest trying again |
