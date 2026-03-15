# Expanded Bookkeeper Commands — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 6 new commands/skills (lookup, fix, delete, resolve-customers, report, undo), update sync to write PrivateNote provenance tags, and update reconcile to do record-by-record consistency checks.

**Architecture:** Each new capability is a command/skill pair backed by Python scripts. Commands are thin .md wrappers. Skills instruct Claude to: (1) call MCP tools to fetch raw data, (2) pipe data through Python scripts for deterministic computation, (3) present results with rich markdown tables and artifacts. All write operations use propose-then-confirm. Audit trail lives in QBO PrivateNote fields.

**Key principle — script maximalism:** All deterministic/algorithmic work (diffing, matching, aggregating, reconciling, formatting comparisons) lives in Python scripts. Claude orchestrates MCP calls, invokes scripts, presents results, and handles the confirmation flow. Claude does NOT do inline computation.

**Key principle — UI maximalism:** Use rich markdown (tables, status indicators, structured output) for all responses. Generate HTML artifacts for visual reports (reconciliation dashboards, tax breakdowns, customer scan results) when running in environments that support them.

**Tech Stack:** Markdown (skills/commands), Python (scripts for all computation), Shopify MCP (`get-customers`, `get-orders`, `get-order`), QBO MCP (`query`, `create_customer`, `create_invoice`, `delete_transaction`, `profit_and_loss`, `balance_sheet`)

**Design doc:** `docs/plans/2026-03-14-expanded-commands-design.md`

---

### Task 1: Update transform scripts to write PrivateNote provenance tags

**Files:**
- Modify: `scripts/transform_customers.py` (add PrivateNote field to output)
- Modify: `scripts/transform_invoices.py` (update existing PrivateNote format)
- Test: `tests/test_transform_customers.py`
- Test: `tests/test_transform_invoices.py`

**Step 1: Write failing test for customer PrivateNote**

Add to `tests/test_transform_customers.py`:

```python
def test_customer_has_private_note_with_shopify_sync_tag():
    """Transformed customers must include [shopify-sync:<gid>] PrivateNote."""
    customer = {
        "id": "gid://shopify/Customer/1001",
        "firstName": "Jane",
        "lastName": "Smith",
        "email": "jane@example.com",
    }
    result = transform_customer(customer)
    assert "PrivateNote" in result
    assert "[shopify-sync:gid://shopify/Customer/1001]" in result["PrivateNote"]
    assert "Imported on" in result["PrivateNote"]
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge && python -m pytest tests/test_transform_customers.py::test_customer_has_private_note_with_shopify_sync_tag -v`
Expected: FAIL — PrivateNote not in result or missing sync tag

**Step 3: Update transform_customers.py**

In `transform_customer()`, add to the output dict:

```python
"PrivateNote": f"[shopify-sync:{customer.get('id', '')}] Imported on {datetime.now().strftime('%Y-%m-%d')}"
```

Import `datetime` at top of file if not already present.

**Step 4: Run test to verify it passes**

Run: `cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge && python -m pytest tests/test_transform_customers.py::test_customer_has_private_note_with_shopify_sync_tag -v`
Expected: PASS

**Step 5: Write failing test for invoice PrivateNote update**

Add to `tests/test_transform_invoices.py`:

```python
def test_invoice_private_note_has_shopify_sync_tag():
    """Invoice PrivateNote must include [shopify-sync:<gid>] provenance tag."""
    order = make_sample_order(order_id="gid://shopify/Order/2001", name="#1001")
    result = transform_invoice(order, tax_mapping=DEFAULT_TAX_MAPPING)
    assert "[shopify-sync:gid://shopify/Order/2001]" in result["PrivateNote"]
    assert "Imported from Shopify order #1001" in result["PrivateNote"]
```

Use existing test helper `make_sample_order` if available; otherwise create a minimal order dict matching the existing test fixtures.

**Step 6: Run test to verify it fails**

Run: `cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge && python -m pytest tests/test_transform_invoices.py::test_invoice_private_note_has_shopify_sync_tag -v`
Expected: FAIL — current PrivateNote is just `"Imported from Shopify order #1001"`, missing sync tag

**Step 7: Update transform_invoices.py**

Change the PrivateNote line (currently around line 194) from:

```python
"PrivateNote": f"Imported from Shopify order {order.get('name', '')}"
```

to:

```python
"PrivateNote": f"[shopify-sync:{order.get('id', '')}] Imported from Shopify order {order.get('name', '')} on {datetime.now().strftime('%Y-%m-%d')}"
```

**Step 8: Run all transform tests**

Run: `cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge && python -m pytest tests/ -v`
Expected: All PASS

**Step 9: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add scripts/transform_customers.py scripts/transform_invoices.py tests/
git commit -m "feat: add [shopify-sync] PrivateNote provenance tags to transform output"
```

---

### Task 2: Update sync skill to pass PrivateNote through to QBO

**Files:**
- Modify: `skills/sync/SKILL.md`

**Step 1: Update the Load phase in sync SKILL.md**

In Phase 3 (Load into QBO), update the customer upsert loop step 4 to explicitly mention passing PrivateNote:

After "If not exists -> create via QBO MCP `create_customer`", add:
```
Include the PrivateNote field from the transformed JSON. This contains
the [shopify-sync:<shopify-gid>] provenance tag that other commands
(lookup, reconcile, resolve-customers, undo) depend on.
```

Similarly for the invoice creation loop step 3, after "Create via QBO MCP `create_invoice`", add:
```
Include the PrivateNote field. It contains the [shopify-sync:<shopify-gid>]
tag and import timestamp needed for audit trail and undo operations.
```

**Step 2: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add skills/sync/SKILL.md
git commit -m "feat: update sync skill to document PrivateNote provenance passthrough"
```

---

### Task 3: Create core Python scripts for computation

All deterministic logic lives in scripts. Claude calls MCP for raw data, passes it to scripts, presents results.

**Files:**
- Create: `scripts/lookup_records.py`
- Create: `scripts/diff_records.py`
- Create: `scripts/scan_customers.py`
- Create: `scripts/generate_report.py`
- Create: `scripts/find_undo_targets.py`
- Test: `tests/test_lookup_records.py`
- Test: `tests/test_diff_records.py`
- Test: `tests/test_scan_customers.py`
- Test: `tests/test_generate_report.py`
- Test: `tests/test_find_undo_targets.py`

#### 3a: `scripts/lookup_records.py`

Takes Shopify + QBO data for one entity, produces a structured side-by-side comparison.

```python
"""Cross-system record comparison.

Usage:
  python lookup_records.py --type customer --shopify shopify_customer.json --qbo qbo_customer.json
  python lookup_records.py --type order --shopify shopify_order.json --qbo qbo_invoice.json

Outputs JSON:
  {
    "entity_type": "customer",
    "shopify": { ... normalized fields ... },
    "qbo": { ... normalized fields ... },
    "comparison": [
      {"field": "Name", "shopify": "Jane Smith", "qbo": "Jane Smith", "match": true},
      {"field": "Tax", "shopify": "6.5%", "qbo": "0%", "match": false}
    ],
    "sync_status": "mismatch",  // "synced" | "mismatch" | "missing_from_qbo" | "missing_from_shopify"
    "mismatches": [{"field": "Tax", "shopify": "6.5%", "qbo": "0%"}],
    "suggested_action": "fix"  // "fix" | "sync" | "resolve-customers" | "none"
  }
"""
```

Write TDD: test for customer match, customer mismatch, order match, order mismatch, missing from QBO, missing from Shopify.

#### 3b: `scripts/diff_records.py`

Takes a Shopify source record + QBO actual record + tax-mapping.json, computes expected QBO state, diffs against actual.

```python
"""Record diffing with expected state computation.

Usage:
  python diff_records.py --type invoice --shopify shopify_order.json --qbo qbo_invoice.json --tax-map tax-mapping.json
  python diff_records.py --type customer --shopify shopify_customer.json --qbo qbo_customer.json

Outputs JSON:
  {
    "record_id": "SH-1042",
    "discrepancies": [
      {
        "field": "TaxCodeRef",
        "actual": "NON",
        "expected": "TAX",
        "severity": "high",
        "description": "Tax code should be TAX (6.5%) based on Shopify tax line 'State Tax'"
      }
    ],
    "proposed_fixes": [
      {
        "action": "update_tax_code",
        "field": "TaxCodeRef",
        "from": "NON",
        "to": "TAX",
        "description": "Update tax code from NON to TAX (6.5%)"
      }
    ],
    "private_note_entry": "[shopify-qbo:fix] Tax updated from NON to TAX (6.5%) on 2026-03-14. Confirmed by user."
  }
"""
```

Reuses transform logic from `transform_invoices.py` and `transform_customers.py` to compute expected state. Write TDD: test tax mismatch, amount mismatch, customer ref mismatch, no discrepancies.

#### 3c: `scripts/scan_customers.py`

Takes full customer lists from both systems, cross-references, categorizes mismatches.

```python
"""Cross-system customer scan.

Usage:
  python scan_customers.py --shopify shopify_customers.json --qbo qbo_customers.json

Outputs JSON:
  {
    "summary": {"shopify_count": 245, "qbo_synced": 238, "qbo_other": 12, "issues": 7},
    "issues": [
      {
        "severity": "high",
        "category": "missing_from_qbo",
        "shopify_email": "john@example.com",
        "shopify_name": "John Doe",
        "proposed_action": "create",
        "description": "Customer in Shopify but not in QBO"
      },
      {
        "severity": "high",
        "category": "duplicate_email",
        "email": "jane@example.com",
        "qbo_records": [{"id": "42", "name": "Jane Smith"}, {"id": "187", "name": "Jane S."}],
        "proposed_action": "merge",
        "description": "2 QBO customers share the same email"
      },
      {
        "severity": "medium",
        "category": "data_mismatch",
        "email": "bob@example.com",
        "field": "DisplayName",
        "shopify_value": "Robert Smith",
        "qbo_value": "Bob Smith",
        "proposed_action": "update",
        "description": "Name differs between systems"
      }
    ]
  }
"""
```

Categorizes: missing_from_qbo, duplicate_email, data_mismatch, orphaned_in_qbo, qbo_only. Sorted by severity. Write TDD: test each category, test empty lists, test all-synced scenario.

#### 3d: `scripts/generate_report.py`

Takes raw data from both systems, produces structured report output for any of the 4 report types.

```python
"""Report generation.

Usage:
  python generate_report.py --type sync-status --shopify-customers sc.json --shopify-orders so.json --qbo-customers qc.json --qbo-invoices qi.json
  python generate_report.py --type reconciliation --shopify-orders so.json --qbo-invoices qi.json
  python generate_report.py --type tax --shopify-orders so.json --qbo-invoices qi.json --tax-map tax-mapping.json
  python generate_report.py --type financial --qbo-pnl pnl.json --qbo-bs bs.json

Outputs JSON with report_type, data tables, summary stats, and warnings.
For artifact generation, also outputs an HTML version to --html-output if specified.
"""
```

Each report type returns structured data Claude can render as rich markdown or an HTML artifact. The `--html-output` flag generates a self-contained HTML dashboard. Write TDD: test each report type with sample data.

#### 3e: `scripts/find_undo_targets.py`

Takes QBO records with PrivateNotes, parses action history, identifies undo targets.

```python
"""Find records to undo based on PrivateNote action history.

Usage:
  python find_undo_targets.py --action sync --date 2026-03-14 --qbo-invoices qi.json --qbo-customers qc.json
  python find_undo_targets.py --action fix --identifier SH-1042 --qbo-invoices qi.json

Outputs JSON:
  {
    "action_to_undo": "sync",
    "date": "2026-03-14",
    "targets": [
      {"type": "invoice", "id": "238", "doc_number": "SH-1042", "action_note": "[shopify-sync:...] Imported on 2026-03-14"},
      {"type": "customer", "id": "42", "name": "Jane Smith", "action_note": "[shopify-sync:...] Imported on 2026-03-14"}
    ],
    "reversal_plan": [
      {"step": 1, "action": "delete_invoice", "id": "238", "doc_number": "SH-1042"},
      {"step": 2, "action": "delete_customer", "id": "42", "name": "Jane Smith"}
    ],
    "warnings": ["Cannot undo deletions — records are permanently removed"]
  }
"""
```

Write TDD: test sync undo, fix undo, no targets found, records with payments (non-deletable).

**Implementation approach for Task 3:**

Build each script + its tests as a sub-task. TDD for each: write failing test, implement, verify pass. Commit after each script is green. Each script reads JSON from stdin or file args, writes JSON to stdout. Scripts share utility functions via a `scripts/utils.py` module for common operations (PrivateNote parsing, field normalization, Shopify GID extraction).

**Step 1: Create `scripts/utils.py` with shared helpers**

```python
"""Shared utilities for shopify-qbo scripts."""

def parse_private_note(note: str) -> list[dict]:
    """Parse PrivateNote into structured action entries.

    Returns list of {"tag": "shopify-sync", "gid": "...", "date": "...", "detail": "..."}
    """

def normalize_shopify_customer(customer: dict) -> dict:
    """Normalize Shopify customer to comparable fields."""

def normalize_qbo_customer(customer: dict) -> dict:
    """Normalize QBO customer to comparable fields."""

def normalize_shopify_order(order: dict) -> dict:
    """Normalize Shopify order to comparable fields."""

def normalize_qbo_invoice(invoice: dict) -> dict:
    """Normalize QBO invoice to comparable fields."""

def format_currency(amount: float) -> str:
    """Format as $X,XXX.XX"""
```

Test utils first, then each script builds on them.

**Commit strategy:** One commit per script+tests pair (5 commits for this task).

---

### Task 4: Create lookup command and skill

**Script integration:** The skill's Step 3 (present comparison) delegates to `scripts/lookup_records.py`. Claude fetches raw data via MCP (Steps 1-2), saves to temp JSON files, runs the script, presents the structured output as rich markdown. For environments supporting artifacts, generate an HTML comparison view.

**Files:**
- Create: `commands/lookup.md`
- Create: `skills/lookup/SKILL.md`

**Step 1: Create command file**

Create `commands/lookup.md`:

```markdown
---
description: "Look up a customer or order across Shopify and QBO. Shows side-by-side comparison with sync status."
argument-hint: "<customer-name|email|order-number|date-range>"
---

Use the `shopify-qbo:lookup` skill to search both systems and compare records.
```

**Step 2: Create skill file**

Create `skills/lookup/SKILL.md`:

```markdown
---
name: lookup
description: >
  Cross-system search across Shopify and QuickBooks Online. Finds customers by
  name or email and orders by number, showing a side-by-side comparison with
  match/mismatch indicators. Use when the user says "find customer", "look up
  order", "search for", "where is", "show me customer X", "check order X",
  or asks about a specific customer or order in either system.
---

# Cross-System Lookup

Search Shopify and QBO simultaneously, present side-by-side comparison.

## Step 1: Parse the Query

Determine what the user is looking for:
- **Email address** (contains @) -> customer lookup by email
- **Order number** (starts with # or is numeric) -> order/invoice lookup
- **Name** (anything else) -> customer lookup by name
- **Date range** ("last week", "March orders") -> order list lookup

## Step 2: Fetch from Both Systems

**Customer lookup:**
- Shopify: `get-customers` with search by name or email
- QBO: `query` with `SELECT Id, DisplayName, GivenName, FamilyName, PrimaryEmailAddr, PrimaryPhone, BillAddr, Notes FROM Customer WHERE PrimaryEmailAddr = '<email>'`
- If searching by name: `WHERE DisplayName LIKE '%<name>%'`

**Order/Invoice lookup:**
- Shopify: `get-orders` filtered to find the order number, or `get-order` if you have the GID
- QBO: `query` with `SELECT Id, DocNumber, TxnDate, TotalAmt, Balance, CustomerRef, TxnTaxDetail, PrivateNote FROM Invoice WHERE DocNumber = 'SH-<number>'`

## Step 3: Run Comparison Script

Save the fetched data to temp JSON files and run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lookup_records.py \
  --type customer \
  --shopify /tmp/shopify_customer.json \
  --qbo /tmp/qbo_customer.json
```

Or for orders:
```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/lookup_records.py \
  --type order \
  --shopify /tmp/shopify_order.json \
  --qbo /tmp/qbo_invoice.json
```

The script outputs structured JSON with field-by-field comparisons, match/mismatch indicators,
sync status, and suggested next actions.

## Step 4: Present Results

Render the script output as a rich markdown table. Use ✓ for matches, ✗ for mismatches.

**Customer fields:** Name, Email, Phone, Address, Tax status, Shopify ID, QBO ID, Sync status.
**Order fields:** Date, Customer, Subtotal, Tax (amount and rate), Shipping, Discounts, Total, Line items.

In environments supporting artifacts, generate an HTML comparison view with color-coded match status.

## Step 4: Suggest Next Actions

Based on findings:
- If mismatch found -> suggest `/shopify-qbo:fix <identifier>`
- If missing from QBO -> suggest `/shopify-qbo:sync`
- If customer mismatch -> suggest `/shopify-qbo:resolve-customers <name>`
- If everything matches -> confirm "✓ In sync"

## Output Style

- Plain English, no JSON or API jargon
- Tables for comparisons
- ✓/✗ indicators for field-level match status
- Always show both system IDs for reference
```

**Step 3: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add commands/lookup.md skills/lookup/SKILL.md
git commit -m "feat: add lookup command and skill for cross-system search"
```

---

### Task 5: Create fix command and skill

**Script integration:** Steps 2-3 (compute expected state, diff) delegate to `scripts/diff_records.py`. Claude fetches raw data via MCP, runs the script, presents the diff and proposed fixes. For artifacts, generate an HTML diff view.

**Files:**
- Create: `commands/fix.md`
- Create: `skills/fix/SKILL.md`

**Step 1: Create command file**

Create `commands/fix.md`:

```markdown
---
description: "Investigate and fix data discrepancies between Shopify and QBO. Proposes corrections and waits for confirmation before writing."
argument-hint: "<order-number|invoice-number|customer-name|description>"
---

Use the `shopify-qbo:fix` skill to investigate and correct data mismatches.
```

**Step 2: Create skill file**

Create `skills/fix/SKILL.md`:

```markdown
---
name: fix
description: >
  Investigate and propose corrections for data discrepancies between Shopify and
  QuickBooks Online. Fetches source data from both systems, computes what QBO
  should have, diffs against actual, and proposes specific fixes with confirmation.
  Use when the user says "fix", "correct", "wrong tax", "update invoice",
  "mismatch", "discrepancy", or describes a data problem between the systems.
---

# Fix Data Discrepancies

Investigate mismatches, propose corrections, execute only after confirmation.

## Step 1: Identify the Record

Parse the user's input to find the record:
- Order/invoice number -> lookup by DocNumber `SH-<number>`
- Customer name/email -> lookup in both systems
- Natural language ("fix the tax on last Tuesday's orders") -> search by date range

Fetch the record from both Shopify and QBO using the same approach as the lookup skill.

## Step 2: Run Diff Script

Save the fetched data to temp JSON files and run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/diff_records.py \
  --type invoice \
  --shopify /tmp/shopify_order.json \
  --qbo /tmp/qbo_invoice.json \
  --tax-map ${CLAUDE_PLUGIN_ROOT}/tax-mapping.json
```

The script computes the expected QBO state using the same transform logic as the sync pipeline,
diffs against the actual QBO record, and outputs structured discrepancies with proposed fixes
and PrivateNote entries.

## Step 3: Present Discrepancies

Render the script output as plain language. Present each discrepancy clearly:

```
Invoice SH-1042:
  Tax Code:   QBO has "NON" (0%), Shopify has "State Tax" -> should be "TAX" (6.5%)
  Tax Amount: QBO has $0.00, should be $7.80
  Total:      QBO has $129.95, should be $137.75
```

## Step 4: Propose Fix

For each discrepancy, state exactly what will change:

```
Proposed fix for Invoice SH-1042:
  1. Update TaxCodeRef from "NON" to "TAX"
  2. Update TxnTaxDetail: add tax line at 6.5% = $7.80
  3. Total will change from $129.95 to $137.75

PrivateNote will be updated with:
  [shopify-qbo:fix] Tax updated from NON to TAX (6.5%) on 2026-03-14. Confirmed by user.

Proceed? (yes/no)
```

**CRITICAL:** Do NOT execute any write until the user explicitly confirms.

## Step 5: Execute Fix

On confirmation:
1. Update the QBO record via the appropriate MCP tool
2. Append to the record's PrivateNote (do not overwrite existing notes)
3. Report the result: "✓ Invoice SH-1042 updated. Tax corrected to 6.5% ($7.80)."

## Scope Limits

**Will fix:**
- Tax code mismatches (wrong TaxCodeRef)
- Tax amount discrepancies
- Customer ref pointing to wrong QBO customer
- Missing or incorrect line items
- Stale customer data (address, phone, email changed in Shopify)

**Will NOT fix (refer to human):**
- Amounts that match between systems (not a sync error)
- Finalized/paid invoices in QBO — flag as needing manual adjustment via QBO UI
- Customer merges — suggest `/shopify-qbo:resolve-customers` instead

## PrivateNote Format

Always append (never overwrite) to existing PrivateNote:
```
[shopify-qbo:fix] <description of change> on <date>. Confirmed by user.
```
```

**Step 3: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add commands/fix.md skills/fix/SKILL.md
git commit -m "feat: add fix command and skill for propose-then-confirm corrections"
```

---

### Task 6: Create delete command and skill

**Files:**
- Create: `commands/delete.md`
- Create: `skills/delete/SKILL.md`

**Step 1: Create command file**

Create `commands/delete.md`:

```markdown
---
description: "Delete a QBO record with safety checks. Shows what will be deleted and requires confirmation. Refuses if payments are linked."
argument-hint: "<invoice-number|DocNumber|customer-name|description>"
---

Use the `shopify-qbo:delete` skill to safely remove records from QuickBooks Online.
```

**Step 2: Create skill file**

Create `skills/delete/SKILL.md`:

```markdown
---
name: delete
description: >
  Safely delete records from QuickBooks Online with confirmation. Looks up the
  record, shows its current state, checks for linked transactions, and requires
  explicit confirmation before executing. Use when the user says "delete",
  "remove", "void", "get rid of", "duplicate invoice", or wants to remove
  a record from QBO.
---

# Safe Record Deletion

Delete QBO records with safety checks and confirmation.

## Step 1: Identify the Record

Parse the user's input:
- DocNumber (e.g., "SH-1042") -> `SELECT * FROM Invoice WHERE DocNumber = 'SH-1042'`
- Customer name -> `SELECT * FROM Customer WHERE DisplayName LIKE '%<name>%'`
- Description -> search by context

Fetch the full record from QBO.

## Step 2: Safety Checks

**For invoices:**
- Check `Balance` vs `TotalAmt` — if Balance < TotalAmt, payments exist
- Check `LinkedTxn` array for linked payments or credit memos
- If payments are linked: **REFUSE** and explain:
  ```
  ⚠ Invoice SH-1042 has $50.00 in payments applied. Cannot delete.
  You must void or remove payments first in the QBO UI, then retry.
  ```

**For customers:**
- Query for invoices referencing this customer: `SELECT COUNT(*) FROM Invoice WHERE CustomerRef = '<id>'`
- If invoices exist: warn that deleting the customer will orphan invoices
- Suggest deleting invoices first or making the customer inactive instead

## Step 3: Present What Will Be Deleted

Show the full record in plain language:

```
About to delete Invoice SH-1042:
  Date:     2026-03-10
  Customer: Jane Smith
  Total:    $137.75
  Status:   Draft (no payments)
  Items:    2 line items + shipping

This cannot be undone. Proceed? (yes/no)
```

**CRITICAL:** Do NOT execute delete until the user explicitly confirms.

## Step 4: Execute Deletion

On confirmation:
1. Call QBO MCP `delete_transaction` with the transaction type and ID
2. If the deleted record referenced a customer, append to that customer's PrivateNote:
   ```
   [shopify-qbo:delete] Invoice SH-1042 deleted on 2026-03-14. Confirmed by user.
   ```
3. Report: "✓ Invoice SH-1042 deleted."
4. Suggest: "Run `/shopify-qbo:sync` to recreate it from Shopify if this was a mistake."

## Important Notes

- Deletions in QBO are permanent — there is no trash/recycle bin
- Always suggest sync as the recovery path for accidentally deleted Shopify-sourced records
- For customers: prefer making inactive over deleting, unless the user specifically wants deletion
```

**Step 3: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add commands/delete.md skills/delete/SKILL.md
git commit -m "feat: add delete command and skill with safety checks"
```

---

### Task 7: Create resolve-customers command and skill

**Script integration:** Scan mode's cross-referencing (Step 2) delegates to `scripts/scan_customers.py`. Claude fetches raw customer lists via MCP, runs the script, presents categorized issues. For artifacts, generate an HTML dashboard of customer health.

**Files:**
- Create: `commands/resolve-customers.md`
- Create: `skills/resolve-customers/SKILL.md`

**Step 1: Create command file**

Create `commands/resolve-customers.md`:

```markdown
---
description: "Find and fix customer mismatches between Shopify and QBO. Scan mode finds all issues; targeted mode investigates one customer."
argument-hint: "[customer-name|email]"
---

Use the `shopify-qbo:resolve-customers` skill to find and resolve customer discrepancies.
```

**Step 2: Create skill file**

Create `skills/resolve-customers/SKILL.md`:

```markdown
---
name: resolve-customers
description: >
  Find and resolve customer mismatches between Shopify and QuickBooks Online.
  Scan mode detects all discrepancies; targeted mode investigates one customer.
  Proposes actions (update, create, link, skip) with confirmation for each.
  Use when the user says "resolve customers", "customer mismatch", "duplicate
  customer", "customer sync issue", "missing customer", "wrong customer",
  or asks about customer consistency between systems.
---

# Resolve Customer Mismatches

Find and fix customer discrepancies between Shopify and QBO.

## Mode Selection

- **No arguments (scan mode):** Find all mismatches across both systems
- **Customer name or email (targeted mode):** Investigate one specific customer

## Scan Mode

### Step 1: Pull All Customers from Both Systems

- Shopify: `get-customers` with pagination (all customers)
- QBO synced: `SELECT Id, DisplayName, PrimaryEmailAddr, GivenName, FamilyName, PrimaryPhone, BillAddr, Notes FROM Customer WHERE Notes LIKE '%shopify-sync%'`
- QBO all: `SELECT Id, DisplayName, PrimaryEmailAddr, Notes FROM Customer`

### Step 2: Run Customer Scan Script

Save the fetched customer lists and run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/scan_customers.py \
  --shopify /tmp/shopify_customers.json \
  --qbo /tmp/qbo_customers.json
```

The script cross-references by email address and categorizes mismatches:

| Category | Criteria | Severity |
|----------|----------|----------|
| **Missing from QBO** | Shopify email not found in any QBO customer | High |
| **Data mismatch** | Email matches but name, phone, or address differs | Medium |
| **Orphaned in QBO** | QBO customer has `[shopify-sync]` tag but email not in Shopify (deleted?) | Medium |
| **QBO-only** | QBO customer without `[shopify-sync]` tag and email not in Shopify | Low (info only) |
| **Duplicate emails** | Multiple QBO customers with the same email | High |

### Step 3: Present Results

Sort by severity (high first). Show a numbered summary:

```
Customer Scan: 245 Shopify, 238 QBO (synced), 12 QBO (other)

⚠ 7 issues found:

  1. [HIGH] Missing from QBO: john@example.com (John Doe) — in Shopify, not in QBO
  2. [HIGH] Duplicate: jane@example.com — 2 QBO records (Customer #42, #187)
  3. [MED]  Name mismatch: bob@example.com — Shopify "Robert Smith" vs QBO "Bob Smith"
  4. [MED]  Address changed: alice@example.com — Shopify address updated
  5. [MED]  Orphaned: old@example.com — in QBO with sync tag, not in Shopify
  6. [LOW]  QBO-only: vendor@supplier.com — not from Shopify (no action needed)
  7. [LOW]  QBO-only: manual@entry.com — not from Shopify (no action needed)

Resolve issues 1-5? (I'll propose each fix individually)
```

### Step 4: Resolve One at a Time

For each issue the user wants to fix, propose an action:

- **Missing from QBO** -> "Create QBO customer from Shopify data? [show fields]"
- **Data mismatch** -> "Update QBO customer to match Shopify? [show diff]"
- **Orphaned** -> "Make QBO customer inactive? Or skip?"
- **Duplicate** -> "Which QBO record to keep? [show both]" Then update the keeper and deactivate the duplicate
- **QBO-only** -> "No action needed (not from Shopify). Skip."

**CRITICAL:** Confirm each action individually before executing.

### Step 5: Execute and Log

On confirmation for each:
1. Execute the write via QBO MCP
2. Append to PrivateNote: `[shopify-qbo:resolve-customers] <action description> on <date>. Confirmed by user.`
3. Report result and move to next issue

## Targeted Mode

Same as scan but filtered to one customer:
1. Search both systems by the provided name or email
2. Show the side-by-side comparison (same format as lookup)
3. If mismatch found, propose fix with confirmation
4. If no issues, report "✓ Customer is in sync"
```

**Step 3: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add commands/resolve-customers.md skills/resolve-customers/SKILL.md
git commit -m "feat: add resolve-customers command and skill for mismatch detection"
```

---

### Task 8: Create report command and skill

**Script integration:** All 4 report types delegate computation to `scripts/generate_report.py`. Claude fetches raw data via MCP, runs the script with `--type` and optional `--html-output` for artifacts. The script returns structured data for markdown rendering and optionally a self-contained HTML dashboard.

**Files:**
- Create: `commands/report.md`
- Create: `skills/report/SKILL.md`

**Step 1: Create command file**

Create `commands/report.md`:

```markdown
---
description: "Generate reports: sync status, financial summaries, reconciliation totals, or tax breakdowns."
argument-hint: "[sync-status|financial|reconciliation|tax] [--date-range START END]"
---

Use the `shopify-qbo:report` skill to generate operational and financial reports.
```

**Step 2: Create skill file**

Create `skills/report/SKILL.md`:

```markdown
---
name: report
description: >
  Unified reporting hub for Shopify-QBO operations. Generates sync status,
  financial summaries, reconciliation totals, and tax breakdowns. Use when
  the user says "report", "show me", "how many synced", "P&L", "profit and
  loss", "balance sheet", "tax summary", "sales tax", "what synced",
  "sync status", or asks for any operational or financial summary.
---

# Reporting Hub

Generate operational and financial reports across both systems.

## Report Type Selection

If the user doesn't specify a type, ask:

```
What kind of report?
  1. Sync status — what's synced, what's pending, recent errors
  2. Financial — P&L, balance sheet from QBO
  3. Reconciliation — Shopify vs QBO totals comparison
  4. Tax — tax collected by jurisdiction with cross-system validation
```

Default to `sync-status` if the user just says "report" without context.

## Date Range

All reports accept an optional date range. Default to current month.
Parse natural language: "last week", "Q1", "March", "last 30 days".

## Data Flow (all report types)

1. Claude fetches raw data via MCP (queries vary by report type — see below)
2. Save raw data to temp JSON files
3. Run: `python ${CLAUDE_PLUGIN_ROOT}/scripts/generate_report.py --type <type> --shopify-orders so.json --qbo-invoices qi.json [--html-output report.html]`
4. Present the script's structured output as rich markdown
5. If `--html-output` was used, offer the HTML as an artifact

## Report: sync-status

### MCP Queries
- QBO synced records: `SELECT Id, DocNumber, PrivateNote FROM Invoice WHERE PrivateNote LIKE '%shopify-sync%'`
- QBO synced customers: `SELECT Id, DisplayName, PrimaryEmailAddr, Notes, PrivateNote FROM Customer`
- Shopify: `get-customers` and `get-orders` (counts)

### Output Format
```
Sync Status — as of 2026-03-14:

                    Shopify     QBO (synced)    Gap
────────────────────────────────────────────────────
Customers           245         238             7 unsynced
Orders/Invoices     1,042       1,038           4 unsynced

Last sync: 2026-03-13
Recent errors: 0

Unsynced customers: Use /shopify-qbo:resolve-customers to investigate.
Unsynced orders: Use /shopify-qbo:lookup to check specific orders.
```

## Report: financial

### Data Gathering
- QBO MCP `profit_and_loss` for the date range
- QBO MCP `balance_sheet` for the date range

### Output Format

Present in plain language with key numbers:
- Revenue (total income)
- Cost of goods / expenses
- Net income
- Sales tax collected
- Accounts receivable balance

No raw JSON. Summarize in a clear table with context.

## Report: reconciliation

### Data Gathering
- Shopify: `get-orders` for the date range, sum totals (subtotal, tax, shipping, grand total)
- QBO: `SELECT DocNumber, TotalAmt, TxnTaxDetail FROM Invoice WHERE TxnDate >= '<start>' AND TxnDate <= '<end>' AND DocNumber LIKE 'SH-%'`
- Count and sum both sides

### Output Format
```
Reconciliation — March 2026:

                    Shopify          QBO              Diff
────────────────────────────────────────────────────────────
Orders/Invoices     142              140              -2 ✗
Subtotal            $28,450.00       $28,450.00       $0.00 ✓
Tax                 $1,849.25        $1,841.45        -$7.80 ✗
Shipping            $1,278.58        $1,278.58        $0.00 ✓
Grand Total         $31,577.83       $31,570.03       -$7.80 ✗

⚠ 2 orders not in QBO: #1042, #1087
⚠ Tax discrepancy of $7.80 — matches missing order #1042
   Use /shopify-qbo:lookup 1042 to investigate.
```

## Report: tax

### Data Gathering
- QBO: Query all invoice tax lines for the date range:
  `SELECT Id, DocNumber, TxnDate, TxnTaxDetail FROM Invoice WHERE TxnDate >= '<start>' AND TxnDate <= '<end>' AND DocNumber LIKE 'SH-%'`
- Parse TxnTaxDetail from each invoice, group by TaxRateRef
- QBO: `SELECT Id, Name, RateValue FROM TaxRate` for rate names
- Shopify: `get-orders` for the same range, extract and group tax lines by title

### Output Format
```
Tax Report — March 2026:

Jurisdiction         Taxable Sales    Tax Collected    Rate     Shopify Match
──────────────────────────────────────────────────────────────────────────────
WA State Tax         $22,180.00       $1,441.70        6.5%     ✓
King County Tax      $22,180.00       $443.60          2.0%     ✓
OR (tax exempt)      $6,270.00        $0.00            0.0%     ✓
Unmapped             $0.00            $0.00            —        —

Total Tax Collected: $1,885.30
QBO Tax Liability:   $1,885.30  ✓ Matches

No discrepancies found.
```

If mismatches found, suggest `/shopify-qbo:fix` for specific invoices or updating `tax-mapping.json` for systematic issues.
```

**Step 3: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add commands/report.md skills/report/SKILL.md
git commit -m "feat: add report command and skill with 4 report types"
```

---

### Task 9: Create undo command and skill

**Script integration:** Step 2 (find affected records) delegates to `scripts/find_undo_targets.py`. Claude fetches QBO records with PrivateNotes via MCP, runs the script to parse action history and compute a reversal plan.

**Files:**
- Create: `commands/undo.md`
- Create: `skills/undo/SKILL.md`

**Step 1: Create command file**

Create `commands/undo.md`:

```markdown
---
description: "Reverse a recent sync, fix, or other action by searching QBO PrivateNote history. Requires confirmation."
argument-hint: "<description of what to undo>"
---

Use the `shopify-qbo:undo` skill to reverse recent actions.
```

**Step 2: Create skill file**

Create `skills/undo/SKILL.md`:

```markdown
---
name: undo
description: >
  Reverse recent shopify-qbo actions by searching QBO PrivateNote history.
  Finds records modified by previous commands (sync, fix, resolve-customers)
  and proposes reversals with confirmation. Use when the user says "undo",
  "revert", "rollback", "take back", "reverse", "shouldn't have", or wants
  to reverse a recent action.
---

# Undo Recent Actions

Reverse previous shopify-qbo operations using PrivateNote history.

## Step 1: Identify What to Undo

Parse the user's description:
- "undo last sync" -> find records with `[shopify-sync]` and today's or recent date
- "undo the fix on order 1042" -> find Invoice SH-1042, look for `[shopify-qbo:fix]` in PrivateNote
- "undo customer resolution" -> find customers with `[shopify-qbo:resolve-customers]` in PrivateNote

## Step 2: Find Affected Records

Query QBO for records matching the action:

**For sync undo:**
```
SELECT Id, DocNumber, PrivateNote FROM Invoice WHERE PrivateNote LIKE '%shopify-sync%' AND PrivateNote LIKE '%<date>%'
SELECT Id, DisplayName, PrivateNote FROM Customer WHERE PrivateNote LIKE '%shopify-sync%' AND PrivateNote LIKE '%<date>%'
```

**For fix undo:**
```
SELECT Id, DocNumber, PrivateNote FROM Invoice WHERE DocNumber = 'SH-<number>' AND PrivateNote LIKE '%shopify-qbo:fix%'
```

**For resolve-customers undo:**
```
SELECT Id, DisplayName, PrivateNote FROM Customer WHERE PrivateNote LIKE '%shopify-qbo:resolve-customers%' AND PrivateNote LIKE '%<date>%'
```

## Step 3: Present Reversal Plan

Show what will be reversed:

```
Undo: fix on Invoice SH-1042 (applied 2026-03-14)

Original fix: Tax updated from NON to TAX (6.5%)

To reverse:
  1. Update TaxCodeRef from "TAX" back to "NON"
  2. Remove tax line from TxnTaxDetail
  3. Append to PrivateNote: "[shopify-qbo:undo] Reverted fix from 2026-03-14"

Proceed? (yes/no)
```

For sync undo (batch):
```
Undo: sync from 2026-03-14

Found 45 invoices and 12 customers created on that date.

To reverse:
  1. Delete 45 invoices (all in draft status ✓)
  2. Delete 12 customers (no linked invoices after step 1 ✓)

⚠ This will remove all records from the March 14 sync. Proceed? (yes/no)
```

**CRITICAL:** Confirm before executing any reversal.

## Step 4: Execute Reversal

On confirmation:
1. Execute writes/deletes via QBO MCP
2. Append to PrivateNote on any surviving records: `[shopify-qbo:undo] Reverted <action> from <date> on <today>. Confirmed by user.`
3. Report results

## Limitations

- **Cannot undo a delete** — the record is gone from QBO. Clearly state:
  "Cannot undo deletion — the record no longer exists in QBO. Run `/shopify-qbo:sync` to recreate it from Shopify."
- **Cannot revert finalized invoices** — if an invoice was finalized after a fix, the undo may fail. Flag this and suggest manual correction.
- **PrivateNote is the only history** — if someone manually edited a record and removed the PrivateNote, undo cannot find it.
```

**Step 3: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add commands/undo.md skills/undo/SKILL.md
git commit -m "feat: add undo command and skill for reversing recent actions"
```

---

### Task 10: Update reconcile skill for record-by-record consistency

**Script integration:** The record-by-record comparison delegates to `scripts/diff_records.py` (per-record) and `scripts/generate_report.py --type reconciliation` (summary). Claude fetches matched pairs via MCP, runs diff_records on each pair, aggregates results.

**Files:**
- Modify: `commands/reconcile.md`
- Modify: `skills/reconcile/SKILL.md`

**Step 1: Update command file**

Update `commands/reconcile.md`:

```markdown
---
description: "Deep record-by-record consistency check between Shopify and QBO. Compares every synced order field-by-field and offers to fix issues."
argument-hint: "[--date-range START END] [--threshold 0.01]"
---

Use the `shopify-qbo:reconcile` skill to run a deep consistency audit across both systems.
```

**Step 2: Rewrite reconcile SKILL.md**

Replace the contents of `skills/reconcile/SKILL.md` with the updated version that does record-by-record comparison instead of just tax totals. The new skill should:

1. Query QBO for all invoices with `[shopify-sync]` PrivateNote (or DocNumber LIKE 'SH-%')
2. For each QBO invoice, fetch the matching Shopify order
3. Compare field-by-field: customer ref, line item count, line amounts, tax codes, tax amounts, shipping, discounts, total
4. Also find Shopify orders missing from QBO entirely
5. Also find QBO invoices with `[shopify-sync]` but no matching Shopify order (orphans)
6. Present a summary with per-record issues
7. Offer to batch-fix via the fix skill (propose-then-confirm, one at a time)

Retain the existing common discrepancy causes table and tax mapping audit section from the current skill — those are still useful.

**Step 3: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add commands/reconcile.md skills/reconcile/SKILL.md
git commit -m "feat: update reconcile to deep record-by-record consistency check"
```

---

### Task 11: Update plugin.json and README

**Files:**
- Modify: `README.md`
- Modify: `.claude-plugin/plugin.json`

**Step 1: Update README.md**

Add the new commands to the command reference table. Update the description to mention bookkeeper workflows.

**Step 2: Update plugin.json**

Add `keywords` that reflect the expanded functionality: `"lookup"`, `"fix"`, `"delete"`, `"resolve"`, `"report"`, `"undo"`, `"bookkeeper"`.

**Step 3: Commit**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git add README.md .claude-plugin/plugin.json
git commit -m "docs: update README and plugin.json for expanded command set"
```

---

### Task 12: Push and update marketplace

**Files:**
- Modify (in my-claude-plugins): `.claude-plugin/marketplace.json` — bump version to 2.0.0
- Modify (in my-claude-plugins): `README.md` — update description

**Step 1: Push ShopifyQuickbooksBridge**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
git push origin main
```

**Step 2: Update marketplace version**

```bash
cd /Users/rwaugh/src/mine/my-claude-plugins
```

Update `marketplace.json` to bump shopify-qbo version from `1.0.0` to `2.0.0` and update the description to mention bookkeeper commands.

**Step 3: Commit and push marketplace**

```bash
cd /Users/rwaugh/src/mine/my-claude-plugins
git add .claude-plugin/marketplace.json README.md
git commit -m "feat: bump shopify-qbo to 2.0.0 with expanded bookkeeper commands"
git push origin main
```

**Step 4: Re-zip for Cowork**

```bash
cd /Users/rwaugh/src/mine/ShopifyQuickbooksBridge
zip -r ~/Desktop/shopify-qbo.zip . -x ".git/*" "*__pycache__/*" "sync_output/*" ".env"
```

Upload the new zip in Cowork to replace the previous version.
