# Shopify -> QuickBooks Online Sync Pipeline

## Implementation Design Document

**Version:** 1.0
**Date:** March 13, 2026
**Status:** Ready for Implementation

## 1. Executive Summary

This document describes a one-way, agentic data synchronization pipeline that exports customers, invoices (from orders), and tax line data from a Shopify store and imports them into QuickBooks Online. The system uses two open-source MCP (Model Context Protocol) servers as API connectors, a Claude skill plugin as the intelligent orchestrator, and a set of Python transformation scripts as the mapping and validation layer.

The architecture is designed so that the MCP servers handle raw API transport, the scripts handle deterministic transformation logic, and the AI agent handles orchestration, error recovery, and judgment calls -- following the same design philosophy used in your Monarch Money MCP retirement planning project: mechanically-classified raw data with interpretive judgment left to the agent.

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| Shopify customers -> QBO customers | Bidirectional sync (QBO -> Shopify) |
| Shopify orders -> QBO invoices | Refunds / credit memos |
| Shopify tax lines -> QBO tax detail | Product/inventory sync |
| Deduplication on import | Payment recording in QBO |
| Tax reconciliation reporting | Multi-currency conversion |
| Audit trail generation | Historical backfill (>12 months) |

## 2. Architecture

### 2.1 System Diagram

```
+---------------------------------------------------------------------------+
|                        Claude Agent (Orchestrator)                         |
|                                                                           |
|   +----------+    +---------------------+    +----------+                 |
|   |  SKILL   |--->|  Python Scripts      |--->|  Audit   |                 |
|   |  .md     |    |  (Transform/Map)     |    |  Report  |                 |
|   +----------+    +---------------------+    +----------+                 |
|        |                    |                                              |
|   +----+----+          +---+---+                                          |
|   | Extract |          | Load  |                                          |
|   +----+----+          +---+---+                                          |
+--------+-------------------+---------------------------------------------|
         |                   |
    +----+------+      +----+------+
    | Shopify   |      |   QBO     |
    | MCP       |      |   MCP     |
    | Server    |      |   Server  |
    +----+------+      +----+------+
         |                   |
    +----+------+      +----+------+
    | Shopify   |      | QuickBooks|
    | Admin API |      | Online    |
    | (GraphQL) |      | (REST)    |
    +-----------+      +-----------+
```

### 2.2 Component Responsibilities

**MCP Servers** -- Stateless API transport. Each server wraps one external API and exposes its operations as MCP tools. The servers handle authentication, token refresh, rate limiting, and serialization. They do not contain business logic.

**Skill Plugin (SKILL.md)** -- The agent's instruction manual. Contains the sync workflow definition, field mapping tables, tax mapping rules, error handling policies, and references to scripts and configuration files. When a user asks to sync Shopify to QBO, this skill triggers and guides the agent through the four-phase pipeline.

**Python Scripts** -- Deterministic transformation layer. Three scripts handle customer mapping, invoice mapping with tax resolution, and end-to-end orchestration with validation. These run locally and produce intermediate JSON files that the agent then loads into QBO via MCP.

**Claude Agent** -- The orchestrator. Reads the skill, calls MCP tools to extract data, runs scripts to transform it, calls MCP tools to load it, and exercises judgment on edge cases (ambiguous tax codes, name collisions, missing fields).

### 2.3 Data Flow (Four Phases)

| Phase | Actor | Input | Output |
|-------|-------|-------|--------|
| 1. Extract | Agent via Shopify MCP | Shopify store (live) | shopify_customers.json, shopify_orders.json |
| 2. Transform | Python scripts | Raw Shopify JSON + tax-mapping.json | qbo_customers.json, qbo_invoices.json |
| 3. Load | Agent via QBO MCP | Transformed QBO JSON | Created/updated records in QBO |
| 4. Validate | Python scripts + Agent | QBO query results + transform stats | sync_audit_{timestamp}.json |

## 3. MCP Server Selection

### 3.1 Evaluation Criteria

Servers were evaluated on: API coverage for required entities (customers, orders, tax), authentication model, community maturity (stars, commits, maintenance), compatibility with Claude Desktop/Code, and safety features.

### 3.2 Shopify MCP: GeLi2001/shopify-mcp

| Attribute | Detail |
|-----------|--------|
| Repository | https://github.com/GeLi2001/shopify-mcp |
| npm Package | shopify-mcp (v1.0.7) |
| npm Weekly Downloads | 330 |
| GitHub Stars | 81+ |
| License | MIT |
| Language | TypeScript / Node.js |
| API | Shopify GraphQL Admin API |
| API Version | 2026-01 (configurable via --apiVersion) |
| Transport | stdio (for Claude Desktop / Claude Code) |
| Auth Models | Static access token (shpat_*) or OAuth client credentials (post-Jan 2026 apps) |

**Why this server over alternatives:**

The @ajackus/shopify-mcp-server has 70+ tools but is a larger surface than needed. The siddhantbajaj/shopify-mcp-server (Python) only exposes products and customers -- no order tools. The official Shopify Dev MCP is for documentation lookup, not store data access. GeLi2001/shopify-mcp hits the sweet spot: full Admin API access for customers, orders, and products via GraphQL, active maintenance, OAuth support for post-January-2026 apps, and the simplest setup (single npx command, no clone required).

**Available Tools (relevant subset):**

| Tool | Description | Use in Pipeline |
|------|-------------|-----------------|
| get-customers | Fetch customers with optional search by name/email, pagination via limit | Extract all customers |
| get-orders | Fetch orders with status/date filtering, pagination | Extract paid orders |
| get-order | Fetch single order by ID with full line item and tax detail | Deep fetch for tax validation |
| get-customer-orders | Fetch all orders for a specific customer | Cross-reference during validation |
| get-products | Fetch products with variant info | Resolve product names for QBO item refs |
| update-customer | Update customer fields (tags, tax exemption, etc.) | Mark synced customers in Shopify |

### 3.3 QBO MCP: laf-rge/quickbooks-mcp

| Attribute | Detail |
|-----------|--------|
| Repository | https://github.com/laf-rge/quickbooks-mcp |
| GitHub Stars | 1+ (newer project) |
| License | MIT |
| Language | TypeScript / Node.js |
| API | QuickBooks Online REST API v3 |
| Transport | stdio |
| Auth | OAuth2 with automatic token refresh |
| Credential Storage | Local (~/.quickbooks-mcp/credentials.json) or AWS Secrets Manager |

**Why this server over alternatives:**

The official intuit/quickbooks-online-mcp-server requires internal QBO IDs for every entity reference -- you need to look up a customer's numeric ID before creating an invoice referencing them. laf-rge/quickbooks-mcp auto-resolves names, so "Create invoice for Jane Smith" works without an ID lookup step. It also has report tools (P&L, Balance Sheet, Trial Balance) that no other QBO MCP provides, which are essential for the tax reconciliation phase. The draft-mode default prevents accidental writes to production books.

vespo92/QBOMCP is a good alternative for its natural language friendliness but has only a single commit and zero stars, making it a maturity risk for production use.

**Available Tools (relevant subset):**

| Tool | Description | Use in Pipeline |
|------|-------------|-----------------|
| query | SQL-like query across any QBO entity | Customer dedup lookups, invoice existence checks |
| create_invoice | Create invoice with line items, tax detail (draft mode default) | Load invoices |
| create_customer | Create customer with auto name resolution | Load customers |
| profit_and_loss | P&L report with date/department breakdown | Tax reconciliation |
| balance_sheet | Balance sheet report | Financial validation |
| delete_transaction | Delete any transaction type | Error recovery |
| qbo_authenticate | Complete OAuth flow (local mode) | Initial setup |
| qbo_company_info | Get company details | Verify connection |

### 3.4 Alternatives Considered

| Server | Pros | Cons | Verdict |
|--------|------|------|---------|
| intuit/quickbooks-online-mcp-server | Official Intuit project, well-tested | Requires internal IDs, no reports, early preview | Good fallback if laf-rge has issues |
| vespo92/QBOMCP | Natural language friendly, smart date parsing | Single commit, 0 stars, unproven | Too immature for production |
| CDataSoftware/quickbooks-mcp-server-by-cdata | Enterprise-grade, JDBC-backed | Read-only, requires commercial JDBC driver license | Read-only is a dealbreaker |
| @ajackus/shopify-mcp-server | 70+ Shopify tools, SSE support | Overkill surface area, less focused | Consider for multi-store scenarios |

## 4. MCP Server Setup Instructions

### 4.1 Prerequisites

- Node.js 18+ installed (`node --version` to verify)
- Python 3.10+ installed (for transformation scripts)
- Claude Desktop or Claude Code installed with MCP support
- A Shopify store with Admin API access
- A QuickBooks Online account with developer access

### 4.2 Shopify MCP Setup

#### Step 1: Create a Shopify Custom App

1. Log into your Shopify Admin dashboard.
2. Navigate to Settings -> Apps and sales channels.
3. Click Develop apps (enable developer preview if prompted).
4. Click Create an app and name it (e.g., "QBO Sync Agent").
5. Go to the Configuration tab -> Admin API integration -> Configure.
6. Grant the following scopes (minimum required):
   - `read_customers`
   - `read_orders`
   - `read_products`
7. Click Save, then go to the API credentials tab.
8. Click Install app.

**For existing apps (pre-January 2026):** Copy the Admin API access token (starts with `shpat_`). You will only see it once.

**For new apps (post-January 2026):** Copy the Client ID and Client Secret from the Dev Dashboard. The MCP server will handle the OAuth token exchange automatically (tokens are valid ~24 hours and auto-refresh).

#### Step 2: Configure the Shopify MCP Server

No installation is needed -- the server runs via npx.

**Option A -- Static access token (legacy apps):**

```json
{
  "mcpServers": {
    "shopify": {
      "command": "npx",
      "args": [
        "shopify-mcp",
        "--accessToken", "shpat_YOUR_ACCESS_TOKEN_HERE",
        "--domain", "your-store.myshopify.com"
      ]
    }
  }
}
```

**Option B -- OAuth client credentials (new apps, recommended):**

```json
{
  "mcpServers": {
    "shopify": {
      "command": "npx",
      "args": [
        "shopify-mcp",
        "--clientId", "YOUR_CLIENT_ID",
        "--clientSecret", "YOUR_CLIENT_SECRET",
        "--domain", "your-store.myshopify.com"
      ]
    }
  }
}
```

**Option C -- Environment variables (CI/CD or shared setups):**

Create a `.env` file:

```
SHOPIFY_ACCESS_TOKEN=shpat_YOUR_TOKEN
MYSHOPIFY_DOMAIN=your-store.myshopify.com
```

Then configure the MCP server without inline credentials:

```json
{
  "mcpServers": {
    "shopify": {
      "command": "npx",
      "args": ["shopify-mcp"],
      "env": {
        "SHOPIFY_ACCESS_TOKEN": "shpat_YOUR_TOKEN",
        "MYSHOPIFY_DOMAIN": "your-store.myshopify.com"
      }
    }
  }
}
```

**For Claude Code (CLI):**

```bash
claude mcp add shopify -- npx shopify-mcp \
  --accessToken shpat_YOUR_TOKEN \
  --domain your-store.myshopify.com
```

#### Step 3: Verify Shopify MCP Connection

Ask Claude: "List my first 3 Shopify products"

If you see product data, the connection is working. If you see an error about `SHOPIFY_ACCESS_TOKEN`, ensure you are using the package `shopify-mcp` (not `shopify-mcp-server` -- a common source of confusion).

### 4.3 QBO MCP Setup

#### Step 1: Create a QuickBooks Online Developer App

1. Go to https://developer.intuit.com and sign in.
2. Click Dashboard -> Create an app.
3. Select QuickBooks Online and Payments.
4. Name it (e.g., "Shopify Sync Agent").
5. Under Scopes, enable `com.intuit.quickbooks.accounting`.
6. Set the Redirect URI to: `https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl`
7. Copy the Client ID and Client Secret.

#### Step 2: Install the QBO MCP Server

```bash
git clone https://github.com/laf-rge/quickbooks-mcp.git
cd quickbooks-mcp
npm install
npm run build
```

#### Step 3: Configure Credentials (Local Mode)

Create the credentials file at `~/.quickbooks-mcp/credentials.json`:

```json
{
  "client_id": "YOUR_QBO_CLIENT_ID",
  "client_secret": "YOUR_QBO_CLIENT_SECRET",
  "redirect_url": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
}
```

Note: `access_token` and `refresh_token` will be populated automatically after the OAuth flow in Step 5.

#### Step 4: Add QBO MCP to Claude Configuration

Add this to your `claude_desktop_config.json` (or Claude Code config):

```json
{
  "mcpServers": {
    "quickbooks": {
      "command": "node",
      "args": ["/absolute/path/to/quickbooks-mcp/dist/index.js"]
    }
  }
}
```

Replace `/absolute/path/to/` with the actual path where you cloned the repo.

**For Claude Code (CLI):**

```bash
claude mcp add quickbooks -- node /absolute/path/to/quickbooks-mcp/dist/index.js
```

#### Step 5: Complete the OAuth Flow

Restart Claude Desktop (or Claude Code), then ask Claude:

"Authenticate with QuickBooks"

The agent will call the `qbo_authenticate` tool, which will:
1. Open a browser window to the Intuit OAuth consent screen.
2. After you authorize, redirect back with an authorization code.
3. Exchange the code for access and refresh tokens.
4. Save both tokens to `~/.quickbooks-mcp/credentials.json`.

Authorization codes expire in a few minutes, so complete this step promptly.

#### Step 6: Verify QBO MCP Connection

Ask Claude: "How many customers do I have in QuickBooks?"

The agent will call the `query` tool with `SELECT COUNT(*) FROM Customer` and return a count. If this works, your QBO MCP is fully operational.

#### Alternative: AWS Secrets Manager (Production)

For shared or production environments, store credentials in AWS Secrets Manager instead of a local file:

```bash
aws secretsmanager create-secret \
  --name prod/qbo \
  --secret-string '{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "access_token": "FROM_OAUTH_FLOW",
    "refresh_token": "FROM_OAUTH_FLOW",
    "redirect_url": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
  }'

aws ssm put-parameter \
  --name /prod/qbo/company_id \
  --value "YOUR_COMPANY_ID" \
  --type SecureString
```

Create a `.env` file in the quickbooks-mcp directory:

```
QBO_CREDENTIAL_MODE=aws
AWS_REGION=us-east-2
QBO_SECRET_NAME=prod/qbo
QBO_COMPANY_ID_PARAM=/prod/qbo/company_id
```

### 4.4 Combined MCP Configuration

The final `claude_desktop_config.json` with both servers:

```json
{
  "mcpServers": {
    "shopify": {
      "command": "npx",
      "args": [
        "shopify-mcp",
        "--accessToken", "shpat_YOUR_SHOPIFY_TOKEN",
        "--domain", "your-store.myshopify.com"
      ]
    },
    "quickbooks": {
      "command": "node",
      "args": ["/absolute/path/to/quickbooks-mcp/dist/index.js"]
    }
  }
}
```

## 5. Skill Plugin Design

### 5.1 Skill Structure

```
shopify-qbo-sync/
  SKILL.md                    # Main skill definition (orchestration logic)
  transform_customers.py      # Shopify customer -> QBO customer
  transform_invoices.py       # Shopify order -> QBO invoice + tax
  orchestrator.py             # Full pipeline: transform -> validate -> report
  agent-playbook.md           # Step-by-step MCP tool call reference
  mcp-servers.md              # MCP setup guide (this section, in portable form)
  field-mapping.md            # Complete field mapping specification
  tax-mapping.json            # Configurable tax code mapping
```

### 5.2 Triggering

The skill triggers when the user mentions any combination of: "shopify sync", "qbo import", "order migration", "customer export", "shopify to quickbooks", "tax mapping", or asks to export Shopify data and import it into QBO. The skill description is deliberately written to be slightly "pushy" to avoid under-triggering.

### 5.3 Installation

**Claude Code (project-level):**

```bash
cp -r shopify-qbo-sync/ <project>/.claude/skills/shopify-qbo-sync/
```

**Claude Code (global):**

```bash
cp -r shopify-qbo-sync/ ~/.claude/skills/shopify-qbo-sync/
```

## 6. Data Mapping Specification

### 6.1 Customer Mapping

| # | Shopify Field | QBO Field | Transform Rule |
|---|---------------|-----------|----------------|
| 1 | firstName + lastName | DisplayName | Concatenate with space. If empty, fall back to email, then to "Shopify Customer {id}" |
| 2 | firstName | GivenName | Direct copy |
| 3 | lastName | FamilyName | Direct copy |
| 4 | email | PrimaryEmailAddr.Address | Direct copy. Also used as dedup key |
| 5 | phone | PrimaryPhone.FreeFormNumber | Direct copy |
| 6 | taxExempt | Taxable | Inverted: Shopify true -> QBO false |
| 7 | defaultAddress.address1 | BillAddr.Line1 | Direct copy |
| 8 | defaultAddress.address2 | BillAddr.Line2 | Direct copy |
| 9 | defaultAddress.city | BillAddr.City | Direct copy |
| 10 | defaultAddress.provinceCode | BillAddr.CountrySubDivisionCode | Prefer provinceCode over province |
| 11 | defaultAddress.zip | BillAddr.PostalCode | Direct copy |
| 12 | defaultAddress.countryCodeV2 | BillAddr.Country | Prefer countryCodeV2 over country |
| 13 | tags | Notes | "Shopify tags: tag1, tag2" |
| 14 | id | Notes (appended) | "Shopify ID: gid://shopify/Customer/123" |

**Deduplication strategy:** Match by email address. Query QBO with `SELECT Id, DisplayName, PrimaryEmailAddr FROM Customer WHERE PrimaryEmailAddr = '{email}'`. If found, compare fields and update if changed; skip if identical. If not found, create new.

**DisplayName uniqueness:** QBO requires unique DisplayName. If a collision is detected, append the email in parentheses: "Jane Smith (jane@example.com)".

### 6.2 Invoice Mapping (from Shopify Order)

| # | Shopify Field | QBO Field | Transform Rule |
|---|---------------|-----------|----------------|
| 1 | name (e.g., "#1001") | DocNumber | Strip non-numeric chars, prefix with "SH-": SH-1001 |
| 2 | createdAt | TxnDate | Truncate ISO timestamp to YYYY-MM-DD |
| 3 | customer.email | CustomerRef.value | Resolve QBO customer ID by email lookup |
| 4 | lineItems[].title | Line[].Description | Direct copy |
| 5 | lineItems[].quantity | Line[].SalesItemLineDetail.Qty | Direct copy (integer) |
| 6 | lineItems[].originalUnitPrice | Line[].SalesItemLineDetail.UnitPrice | Direct copy (decimal) |
| 7 | (computed: qty x price) | Line[].Amount | Calculated, rounded to 2 decimal places |
| 8 | lineItems[].taxLines[0].title | Line[].SalesItemLineDetail.TaxCodeRef.value | Resolved via tax-mapping.json |
| 9 | shippingLines[].price | Separate Line[] entry | TaxCodeRef: "NON", description: "Shipping: {title}" |
| 10 | totalDiscounts | DiscountLineDetail | Separate line, PercentBased: false |
| 11 | taxLines[].title | TxnTaxDetail.TaxLine[].TaxRateRef | Resolved via tax-mapping.json |
| 12 | taxLines[].rate | TxnTaxDetail.TaxLine[].TaxPercent | Multiply by 100: 0.065 -> 6.5 |
| 13 | taxLines[].price | TxnTaxDetail.TaxLine[].Amount | Direct copy |
| 14 | totalTax | TxnTaxDetail.TotalTax | Direct copy |

**Deduplication strategy:** Match by DocNumber. Query QBO with `SELECT Id, DocNumber FROM Invoice WHERE DocNumber = 'SH-{order_number}'`. If found, skip (Shopify orders are immutable). If not found, create new.

**CustomerRef resolution:** Before creating an invoice, the agent must look up the QBO customer ID by email. If the customer doesn't exist in QBO yet, the agent creates them first using the customer mapping above.

### 6.3 Tax Mapping

Tax mapping is configured in `tax-mapping.json` and resolved at transform time. The file contains:

**Regional mappings** -- direct title-to-code lookups organized by country:

| Region | Shopify Tax Title | QBO Tax Code |
|--------|-------------------|-------------|
| US | "State Tax", "Sales Tax", "WA State Tax" | TAX |
| CA | "GST", "GST/HST" | GST, HST |
| CA | "PST", "QST" | PST, QST |
| GB | "VAT" | 20.0% S |
| AU | "GST" | GST |

**Defaults** -- fallback codes when no specific mapping matches:

| Condition | QBO Tax Code |
|-----------|-------------|
| Taxable (no specific match) | TAX |
| Tax exempt / 0% | NON |
| Shipping lines | NON |
| Unknown tax title | TAX (flagged for review) |

**Tax rate conversion:** Shopify stores rates as decimals (e.g., 0.065). QBO stores them as percentages (e.g., 6.5). The transform script multiplies by 100.

**Tax exemption:** If a Shopify customer has `taxExempt: true`, all invoice lines for that customer use `TaxCodeRef: "NON"` regardless of the order's tax lines.

## 7. Pipeline Execution Detail

### 7.1 Phase 1: Extract from Shopify

The agent calls Shopify MCP tools to pull raw data:

**Customers:**

```
Tool: get-customers
Params: { "limit": 250 }
```

Paginate if more than 250 customers exist. Save the complete response array to `shopify_customers.json`.

**Orders:**

```
Tool: get-orders
Params: { "limit": 250, "status": "any" }
```

Paginate as needed. The transform script will filter by `financialStatus` during Phase 2. Save to `shopify_orders.json`.

### 7.2 Phase 2: Transform

Run the orchestrator script:

```bash
python orchestrator.py \
    --shopify-customers shopify_customers.json \
    --shopify-orders shopify_orders.json \
    --tax-map tax-mapping.json \
    --output-dir sync_output \
    --status-filter paid \
    --mode transform-only
```

This produces:
- `sync_output/qbo_customers.json` -- QBO-ready customer objects with metadata
- `sync_output/qbo_invoices.json` -- QBO-ready invoice objects with tax detail
- `sync_output/sync_audit_{timestamp}.json` -- pre-load validation report

The orchestrator runs three sub-steps internally:
1. **transform_customers.py** -- maps all customer fields, deduplicates display names, tracks stats
2. **transform_invoices.py** -- maps order fields, resolves tax codes via mapping file, builds QBO TxnTaxDetail structures, computes line amounts, filters by financial status
3. **Cross-validation** -- checks that all invoice customer emails exist in the customer set, checks for duplicate DocNumbers, compares tax totals between Shopify and transformed QBO amounts

### 7.3 Phase 3: Load into QBO

The agent processes each record from the transformed JSON files through QBO MCP:

**Customer upsert loop** (for each customer in qbo_customers.json):

1. Check existence:
   ```
   Tool: query
   SQL: SELECT Id, DisplayName, PrimaryEmailAddr FROM Customer
        WHERE PrimaryEmailAddr = 'jane@example.com'
   ```
2. If exists -> compare fields. If changed, update. If identical, skip.
3. If not exists -> create:
   ```
   "Create customer Jane Smith, email jane@example.com,
    phone +1-555-0100, billing address 123 Main St, Seattle WA 98101, taxable"
   ```
   (The laf-rge/quickbooks-mcp server supports natural language creation with auto name resolution.)

**Invoice creation loop** (for each invoice in qbo_invoices.json):

1. Check existence:
   ```
   Tool: query
   SQL: SELECT Id, DocNumber FROM Invoice WHERE DocNumber = 'SH-1001'
   ```
2. If exists -> skip (orders are immutable in Shopify).
3. If not exists:
   - Resolve CustomerRef by looking up the QBO customer ID via email
   - Create invoice in draft mode (default) with full line items and tax detail
   - Log the created QBO Invoice ID for audit

### 7.4 Phase 4: Validate and Report

After all records are loaded:

1. **Tax reconciliation:** Sum all QBO invoice tax amounts. Compare against Shopify order tax totals from the transform stats. Flag discrepancies greater than $0.01.
2. **Completeness check:** Compare created/skipped/error counts against expected totals.
3. **Generate audit report:** Write final `sync_audit_{timestamp}.json` with:
   - Customers: created, updated, skipped, errored
   - Invoices: created, skipped (duplicate), errored
   - Tax: Shopify total, QBO total, discrepancy
   - Action items for any issues requiring manual review

## 8. Error Handling

| Error Type | Detection | Response |
|-----------|-----------|----------|
| Duplicate customer | Email already exists in QBO | Compare and update if changed, skip if identical |
| Duplicate invoice | DocNumber already exists in QBO | Skip -- orders are immutable |
| DisplayName collision | QBO rejects non-unique DisplayName | Append email in parentheses and retry |
| Customer not found for invoice | Email lookup returns empty | Create customer first from order billing info, tag as "Shopify Guest" |
| Unknown tax code | No mapping match in tax-mapping.json | Default to "TAX", flag in audit report for manual review |
| Tax discrepancy | Shopify total != QBO total (after load) | Flag in audit report with amounts |
| Shopify rate limit | HTTP 429 from Shopify API | Wait 2 seconds, retry (burst: 40 req/s, sustained: 2 req/s) |
| QBO rate limit | HTTP 429 from QBO API | Wait 60 seconds, retry (limit: 500 req/min) |
| QBO auth expired | OAuth token refresh failure | Re-run `qbo_authenticate` tool |
| Single record failure | Any API error on one record | Log error, continue to next record. Do not abort batch. |
| Guest checkout | Order has no associated customer account | Create QBO customer from order billing email + name |

## 9. Rate Limiting Strategy

| System | Limit | Strategy |
|--------|-------|----------|
| Shopify Admin API | 40 requests/second burst, 2 req/s sustained (leaky bucket) | 100ms delay between calls |
| QBO API | 500 requests/minute, 10 concurrent | 200ms delay between calls |

For a typical store with 500 customers and 1,000 orders:
- **Extract phase:** ~8 API calls (paginated at 250/page) -> ~2 seconds
- **Load phase (worst case, all new):** 500 customer lookups + 500 creates + 1,000 invoice lookups + 1,000 creates = 3,000 calls -> ~10 minutes at 200ms spacing
- **Total estimated runtime:** ~12 minutes for a full initial sync

Subsequent syncs (incremental) would skip existing records and complete in proportionally less time.

## 10. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Shopify access tokens in config | Use environment variables or .env files, never commit tokens to version control |
| QBO OAuth credentials | Store in ~/.quickbooks-mcp/credentials.json (local) or AWS Secrets Manager (production) |
| Sensitive data in transit | Both APIs use HTTPS/TLS. MCP servers communicate via stdio (local pipe, no network) |
| Scope minimization | Shopify app: read-only scopes (read_customers, read_orders, read_products). No write scopes needed for the source system |
| QBO draft mode | All writes default to draft/preview. Agent must explicitly commit. Prevents accidental entries |
| Audit trail | Every sync generates a timestamped JSON report with complete operation log |
| Token rotation | QBO MCP auto-refreshes OAuth tokens on each request. Shopify OAuth tokens are valid ~24 hours and auto-refresh |

## 11. Testing Strategy

### 11.1 Sandbox Testing

**Shopify:** Use a Shopify development store (free from Shopify Partners) with sample data. Populate with 5-10 customers and 10-20 orders covering edge cases (tax exempt customers, multi-line orders, discounts, shipping, guest checkouts).

**QBO:** Use the QuickBooks Online sandbox environment. Set `QUICKBOOKS_ENVIRONMENT=sandbox` in the Intuit developer app. All API calls go to sandbox data -- no risk to production books.

### 11.2 Unit Testing

Run the transform scripts on the provided sample data:

```bash
python orchestrator.py \
    --shopify-customers test_customers.json \
    --shopify-orders test_orders.json \
    --tax-map tax-mapping.json \
    --output-dir test_output \
    --mode transform-only
```

Verify:
- Customer count matches (input = output)
- Tax exempt customers have `Taxable: false`
- Invoice DocNumbers follow the `SH-{number}` pattern
- Tax amounts match between Shopify input and QBO output (discrepancy = $0.00)
- Discount lines are created for orders with discounts
- Shipping lines have `TaxCodeRef: "NON"`

### 11.3 Integration Testing

With both MCP servers configured against sandbox environments:

1. Ask Claude: "Sync my Shopify customers and orders to QuickBooks Online"
2. Verify the agent follows the four-phase pipeline
3. Check QBO sandbox for created customers and draft invoices
4. Review the audit report for any flagged issues
5. Verify tax reconciliation passes

## 12. Future Enhancements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| Incremental sync | Use Shopify `updated_at` filter to only pull new/changed records since last sync | High |
| Refund handling | Map Shopify refunds to QBO Credit Memos | Medium |
| Product/Item sync | Map Shopify products to QBO Items for better invoice line item resolution | Medium |
| Webhook triggers | Listen for Shopify order webhooks to trigger real-time sync | Medium |
| Multi-currency | Handle orders in non-home currencies with exchange rate lookup | Low |
| Payment recording | Record Shopify payments as QBO Payment objects linked to invoices | Low |
| Bidirectional sync | Allow QBO customer updates to flow back to Shopify | Low |

## 13. File Inventory

| File | Size | Purpose |
|------|------|---------|
| SKILL.md | ~4 KB | Skill plugin definition with workflow and references |
| transform_customers.py | ~4 KB | Shopify customer -> QBO customer transformer |
| transform_invoices.py | ~9 KB | Shopify order -> QBO invoice transformer with tax mapping |
| orchestrator.py | ~8 KB | End-to-end pipeline: transform -> validate -> audit report |
| agent-playbook.md | ~5 KB | Step-by-step MCP tool call reference for the agent |
| mcp-servers.md | ~5 KB | MCP server setup and configuration guide |
| field-mapping.md | ~8 KB | Complete field mapping specification with JSON examples |
| tax-mapping.json | ~2 KB | Configurable tax code mapping (US, CA, GB, AU, EU) |
| DESIGN.md | ~25 KB | This document |
| README.md | ~4 KB | Project overview and quick start |

## Appendix A: Sample Transformed Output

### Customer (QBO-ready)

```json
{
  "DisplayName": "Jane Smith",
  "GivenName": "Jane",
  "FamilyName": "Smith",
  "Taxable": true,
  "PrimaryEmailAddr": { "Address": "jane@example.com" },
  "PrimaryPhone": { "FreeFormNumber": "+1-555-0100" },
  "BillAddr": {
    "Line1": "123 Main St",
    "Line2": "Suite 4",
    "City": "Seattle",
    "CountrySubDivisionCode": "WA",
    "PostalCode": "98101",
    "Country": "US"
  },
  "Notes": "Shopify tags: wholesale, vip | Shopify ID: gid://shopify/Customer/1001"
}
```

### Invoice (QBO-ready)

```json
{
  "DocNumber": "SH-1001",
  "TxnDate": "2025-03-15",
  "Line": [
    {
      "DetailType": "SalesItemLineDetail",
      "Amount": 59.98,
      "Description": "Premium Widget",
      "SalesItemLineDetail": {
        "ItemRef": { "value": "1", "name": "Sales" },
        "Qty": 2,
        "UnitPrice": 29.99,
        "TaxCodeRef": { "value": "TAX" }
      }
    },
    {
      "DetailType": "SalesItemLineDetail",
      "Amount": 9.99,
      "Description": "Shipping: Standard Shipping",
      "SalesItemLineDetail": {
        "ItemRef": { "value": "1", "name": "Shipping" },
        "Qty": 1,
        "UnitPrice": 9.99,
        "TaxCodeRef": { "value": "NON" }
      }
    },
    {
      "DetailType": "DiscountLineDetail",
      "Amount": 5.0,
      "DiscountLineDetail": { "PercentBased": false }
    }
  ],
  "TxnTaxDetail": {
    "TotalTax": 3.90,
    "TaxLine": [
      {
        "Amount": 3.90,
        "DetailType": "TaxLineDetail",
        "TaxLineDetail": {
          "TaxRateRef": { "value": "TAX" },
          "PercentBased": true,
          "TaxPercent": 6.5
        }
      }
    ]
  },
  "PrivateNote": "Imported from Shopify order #1001"
}
```

### Audit Report (excerpt)

```json
{
  "report_type": "shopify_qbo_sync_audit",
  "generated_at": "2026-03-14T03:00:29Z",
  "phases": {
    "transform": {
      "customers": { "total_input": 2, "total_output": 2, "tax_exempt_count": 1 },
      "invoices": { "total_input": 1, "total_output": 1, "total_tax": 3.90 }
    },
    "validate": {
      "valid": true,
      "summary": {
        "total_tax_mapped": 3.90,
        "total_shopify_tax_original": 3.90,
        "tax_discrepancy": 0.00
      }
    }
  },
  "action_items": ["No issues found -- ready for QBO import"]
}
```

## Appendix B: Customizing Tax Mapping

Edit `tax-mapping.json` to add your jurisdiction's tax titles. The structure supports:

**Direct title match** -- fastest lookup, exact string match:

```json
{
  "mappings": {
    "US": {
      "WA State Tax": "TAX",
      "King County Tax": "TAX"
    }
  }
}
```

**Partial match** -- the transform script also tries substring matching, so "WA" in the mapping will match "WA State Tax" in Shopify.

**Rate overrides** -- for cases where auto-detection fails, force a specific QBO TaxRate ID:

```json
{
  "rate_overrides": {
    "WA State Tax": {
      "qbo_tax_code": "TAX",
      "qbo_tax_rate_id": "3"
    }
  }
}
```

To find your QBO tax rate IDs, ask Claude: "Query my QBO tax rates: `SELECT Id, Name, RateValue FROM TaxRate`"

## Appendix C: Glossary

| Term | Definition |
|------|-----------|
| MCP | Model Context Protocol -- an open standard for connecting AI assistants to external tools and data sources |
| MCP Server | A process that exposes an API's operations as MCP tools, callable by an AI agent |
| Skill Plugin | A markdown file that instructs Claude on how to perform a multi-step workflow |
| stdio transport | The MCP communication mode where the server runs as a local subprocess and communicates via stdin/stdout pipes |
| OAuth2 | The authorization framework used by QBO. The MCP server handles token exchange and refresh automatically |
| DocNumber | QBO's external reference number for an invoice -- used as the dedup key (format: SH-{order_number}) |
| TxnTaxDetail | QBO's invoice-level tax structure containing individual tax lines with rates and amounts |
| Draft mode | QBO creation mode where records are saved but not finalized -- can be reviewed before committing |
