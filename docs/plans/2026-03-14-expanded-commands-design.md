# Expanded Commands Design — shopify-qbo Plugin

**Date:** 2026-03-14
**Status:** Approved
**Audience:** Bookkeeper (non-technical, guided workflows)

## Design Principles

- **Propose-then-confirm**: Every write operation shows what will change and waits for explicit confirmation before executing.
- **Plain language**: No JSON, no API jargon. Tables and plain English.
- **PrivateNote as audit trail**: All sync provenance and action history lives in QBO PrivateNote fields. No local JSON audit files.
- **Cross-system by default**: Commands search/compare both Shopify and QBO unless the operation is system-specific.
- **Natural language + slash commands**: Skills trigger on conversational descriptions; slash commands provide shortcuts for common tasks.

## PrivateNote Convention

All synced records get a provenance tag in QBO PrivateNote:

```
[shopify-sync:gid://shopify/Customer/1001] Imported on 2026-03-14
```

All corrections append to the same field:

```
[shopify-qbo:fix] Tax updated from NON to TAX (6.5%) on 2026-03-15. Confirmed by user.
```

This enables:
- `resolve-customers` scan: `WHERE Notes LIKE '%shopify-sync%'` finds synced, inverse finds orphans
- `undo`: search PrivateNotes for recent actions by command name and date
- `reconcile`: identify which QBO records came from Shopify

## Interaction Pattern

All new skills follow the same flow:

1. Bookkeeper describes the problem (natural language or slash command)
2. Claude investigates — fetches data from both systems via MCP
3. Claude presents findings in plain language
4. Claude proposes a specific action with a clear summary of what will change
5. Bookkeeper confirms ("yes", "no", "modify")
6. Claude executes and reports the result
7. Claude updates PrivateNote on affected QBO records

## Command Set

### Existing Commands (5)

| Command | Change |
|---------|--------|
| `/shopify-qbo:setup` | No change |
| `/shopify-qbo:configure` | No change |
| `/shopify-qbo:sync` | Updated: writes `[shopify-sync:<gid>]` PrivateNote on all created records |
| `/shopify-qbo:reconcile` | Updated: deep record-by-record consistency check (see below) |
| `/shopify-qbo:status` | No change |

### New Commands (6)

| Command | Skill | Purpose |
|---------|-------|---------|
| `/shopify-qbo:lookup` | `lookup` | Cross-system customer/order search |
| `/shopify-qbo:fix` | `fix` | Investigate and propose corrections |
| `/shopify-qbo:delete` | `delete` | Guided deletion with safety checks |
| `/shopify-qbo:resolve-customers` | `resolve-customers` | Scan or targeted customer mismatch resolution |
| `/shopify-qbo:report` | `report` | Unified reporting hub (4 types) |
| `/shopify-qbo:undo` | `undo` | Reverse recent actions using PrivateNote history |

## Command Details

### `/shopify-qbo:lookup <query>`

Cross-system search. Accepts customer name, email, order number, or date range.

**Resolution logic:**
1. Parse query to determine entity type (customer vs order/invoice)
2. Customer: search Shopify `get-customers` by name/email AND QBO `query` by DisplayName/PrimaryEmailAddr
3. Order: search Shopify `get-orders` by number AND QBO `query` by DocNumber (SH-{number})
4. Present side-by-side comparison table with match/mismatch indicators

**Output includes:** Name, email, phone, address, tax status, IDs, and sync status for customers. Date, customer, subtotal, tax, shipping, total for orders.

### `/shopify-qbo:fix <order-number-or-description>`

Investigate and propose corrections. Accepts order number, invoice number, customer name, or natural language.

**Investigation flow:**
1. Fetch Shopify source data (order, customer, tax lines)
2. Fetch QBO record (invoice, customer)
3. Run transform logic to compute what QBO should have
4. Diff actual vs expected
5. Present each discrepancy with a proposed correction
6. Wait for confirmation per fix

**Can fix:** Tax code mismatches, tax amount discrepancies, wrong customer ref, missing/wrong line items, stale customer data.

**Won't fix (refers to human):** Matching amounts (not a sync error), finalized/paid invoices, customer merges (use `resolve-customers`).

**PrivateNote on corrected records:**
```
[shopify-qbo:fix] Tax updated from NON to TAX (6.5%) on 2026-03-15. Confirmed by user.
```

### `/shopify-qbo:delete <identifier>`

Guided deletion with safety checks.

1. Look up record in QBO by DocNumber, customer name, or description
2. Show current state: draft vs finalized, linked transactions
3. If invoice has linked payments: warn and refuse — bookkeeper must void manually
4. On confirmation: call `delete_transaction`
5. Append PrivateNote to related customer: "Invoice SH-1042 deleted on 2026-03-14, confirmed by user"

### `/shopify-qbo:resolve-customers`

Two modes:

**Scan mode** (no args): Query both systems, find all mismatches — email in Shopify but not QBO, name differences, duplicate emails, orphaned QBO customers without `[shopify-sync]` PrivateNote. Present numbered list sorted by severity.

**Targeted mode** (`resolve-customers Jane Smith`): Investigate one customer across both systems.

**Proposed actions per mismatch:**
- **Update**: QBO customer has stale data, update from Shopify
- **Create**: Shopify customer missing from QBO, create it
- **Link**: Same person, different email/name — update one system to match
- **Skip**: QBO-only customer (not from Shopify), leave alone

Processes one at a time with confirmation.

### `/shopify-qbo:report [type]`

Four report types:

**`sync-status`** (default): Query QBO for records with `shopify-sync` PrivateNotes, compare against Shopify counts. Shows total synced, unsynced, errors, last sync date.

**`financial`**: Call QBO `profit_and_loss` and `balance_sheet` for a date range (defaults to current month). Present in plain language: revenue, expenses, net income, sales tax collected.

**`reconciliation`**: High-level totals comparison. Pull Shopify order totals and QBO invoice totals for a date range. Compare order count, subtotals, tax, shipping, grand totals. Flag discrepancies > $0.01.

**`tax`**: Query QBO invoice tax lines for a date range. Group by jurisdiction/code. Show taxable sales, tax collected, effective rate per code. Cross-reference against Shopify tax lines. Flag rate mismatches between systems.

### `/shopify-qbo:reconcile` (updated)

Deep record-by-record consistency check. Distinct from `report reconciliation` (totals only).

1. Walk every Shopify order with a matching QBO invoice (matched by DocNumber)
2. Compare field-by-field: customer ref, line items, amounts, tax codes, tax amounts
3. Report each inconsistency found
4. Offer to batch-fix via `fix` (still propose-then-confirm, one at a time)

Also identifies:
- Shopify orders missing from QBO entirely
- QBO invoices with `[shopify-sync]` PrivateNote but no matching Shopify order (orphans)

### `/shopify-qbo:undo <description>`

Reverse recent actions using PrivateNote history.

1. Parse description: "undo last sync", "undo the fix on order 1042"
2. Query QBO for records with matching PrivateNotes (command name + identifier + recent date)
3. Present what will be reversed and how (delete invoice, revert customer fields)
4. On confirmation: execute reversal, update PrivateNote with "Reverted on {date}"

**Limitation:** Cannot undo a delete (record is gone from QBO). Skill says so clearly and suggests re-running sync to recreate.

## Changes to Existing Sync Pipeline

The `/shopify-qbo:sync` command needs one update:

**PrivateNote on all created records:**
- Customers: `[shopify-sync:gid://shopify/Customer/{id}] Imported on {date}`
- Invoices: `[shopify-sync:gid://shopify/Order/{id}] Imported from Shopify order #{number} on {date}`

This is a change to the Python transform scripts (`transform_customers.py`, `transform_invoices.py`) to include PrivateNote in the output JSON, and a change to the sync skill's load phase to pass it through to QBO MCP.
