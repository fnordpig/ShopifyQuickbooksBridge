---
name: resolve-customers
description: >
  Scan for and resolve customer discrepancies between Shopify and QuickBooks
  Online. Two modes: full scan (no arguments) finds all issues, or targeted mode
  (name/email) investigates a specific customer. Handles duplicates, missing
  customers, data mismatches, and orphaned records. Use when the user says
  "resolve customers", "customer mismatch", "duplicate customer",
  "missing customer", "customer sync issues", or "clean up customers".
---

# Resolve Customer Discrepancies

Find and fix customer data issues between Shopify and QBO. Operates in two modes:
**scan** (no arguments) or **targeted** (specific customer name or email).

## Mode 1: Full Scan (No Arguments)

### Step 1: Fetch All Customers from Both Systems

Shopify MCP:
```
get-customers with limit: 250 (paginate if needed)
```

QBO MCP:
```
SELECT Id, DisplayName, PrimaryEmailAddr, Active, Balance, PrivateNote
FROM Customer MAXRESULTS 1000
```

### Step 2: Run the Scan Script

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/scan_customers.py \
  --shopify-customers '<shopify_json>' \
  --qbo-customers '<qbo_json>'
```

The script categorizes issues into five buckets.

### Step 3: Present Categorized Results

**Missing from QBO** — Shopify customers with no matching QBO record:

| # | Shopify Customer | Email | Shopify GID | Action |
|---|-----------------|-------|-------------|--------|
| 1 | Jane Doe | jane@example.com | gid://...123 | Create in QBO |
| 2 | Bob Smith | bob@example.com | gid://...456 | Create in QBO |

**Duplicate Email** — Multiple QBO customers sharing an email:

| # | Email | QBO Customers | Action |
|---|-------|--------------|--------|
| 1 | jane@example.com | Jane Doe (Id:12), J. Doe (Id:45) | Merge or inactivate duplicate |

**Data Mismatch** — Same customer in both systems with differing fields:

| # | Customer | Field | Shopify | QBO | Action |
|---|----------|-------|---------|-----|--------|
| 1 | Jane Doe | Phone | 555-0100 | (empty) | Update QBO |
| 2 | Bob Smith | Email | bob@new.com | bob@old.com | Update QBO |

**Orphaned in QBO** — QBO customers with a `[shopify-sync:gid]` tag whose
Shopify GID no longer exists:

| # | QBO Customer | Shopify GID (stale) | Action |
|---|-------------|-------------------|--------|
| 1 | Old Customer | gid://...789 | Inactivate or remove tag |

**QBO Only** — QBO customers without a `[shopify-sync:gid]` tag (may be
manually created or from another source):

| # | QBO Customer | Email | Action |
|---|-------------|-------|--------|
| 1 | Manual Corp | manual@corp.com | No action (not from Shopify) |

Present a summary count:

```
Customer Scan Summary
---------------------
Missing from QBO:    2
Duplicate email:     1
Data mismatch:       2
Orphaned in QBO:     1
QBO only:            5
Total issues:        6 (excluding QBO-only)
```

### Step 4: Resolve One at a Time

Work through issues in priority order:
1. Missing from QBO (blocking for invoice sync)
2. Duplicate email (causes sync confusion)
3. Data mismatch (stale data)
4. Orphaned in QBO (cleanup)

For each issue, propose the fix and wait for confirmation before proceeding.

**Creating a missing customer:**

> **Proposed: Create customer in QBO**
> - DisplayName: Jane Doe
> - Email: jane@example.com
> - Phone: 555-0100
> - PrivateNote: [shopify-sync:gid://shopify/Customer/123]
>
> **Proceed? (yes/no)**

**Resolving a duplicate:**

> **Proposed: Resolve duplicate email jane@example.com**
> - Keep: Jane Doe (Id:12) — has 5 invoices, created 2025-01-01
> - Inactivate: J. Doe (Id:45) — has 0 invoices, created 2026-03-01
>
> **Proceed? (yes/no)**

**Fixing a data mismatch:**

> **Proposed: Update customer Jane Doe in QBO**
> - Phone: (empty) -> 555-0100
>
> **Proceed? (yes/no)**

After each confirmed action, update the PrivateNote:
```
[shopify-qbo:resolve-customers] <action> on <date>
```

## Mode 2: Targeted (Name or Email Argument)

### Step 1: Search Both Systems

Use the same queries as Mode 1 but filtered to the specific customer.

### Step 2: Present Findings

Show the same categorized analysis but for just that customer. If the customer
is clean (present in both systems, data matches), report: "Customer is in sync
across both systems — no issues found."

### Step 3: Resolve

Same propose-then-confirm flow as Mode 1.

## Error Handling

| Error | Action |
|-------|--------|
| No customers in Shopify | "No Shopify customers found. Is the store connected?" |
| No customers in QBO | "No QBO customers found. Run `/shopify-qbo:sync --customers-only` first." |
| Customer has linked invoices (for merge) | Show invoices and ask which customer to reassign them to |
| DisplayName collision on create | Append email in parentheses, e.g., "Jane Doe (jane@example.com)" |
