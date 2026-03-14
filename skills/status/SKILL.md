---
name: status
description: >
  Check the health and configuration status of the Shopify-QBO sync pipeline.
  Verifies MCP server connections, API credentials, and reports what's configured.
  Use when the user says "status", "check connection", "is it working", "verify setup",
  "test connection", "health check", or encounters errors and wants to diagnose.
---

# Connection Status & Health Check

Quickly verify the sync pipeline is operational.

## Run Checks

### 1. Environment

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/check_env.py
```

Reports: prerequisites, existing MCP configs, QBO credential status.

### 2. Shopify Connection

Test by calling the Shopify MCP:
```
get-products with limit: 1
```

| Result | Status | Action |
|--------|--------|--------|
| Returns product data | Connected | None |
| "Unauthorized" | Token expired/invalid | Run `/shopify-qbo:configure shopify` |
| "Not found" | Domain wrong | Check store domain |
| Tool not available | MCP not configured | Run `/shopify-qbo:setup` |

### 3. QBO Connection

Test by calling the QBO MCP:
```
query: SELECT CompanyName FROM CompanyInfo
```

| Result | Status | Action |
|--------|--------|--------|
| Returns company name | Connected | None |
| "Token expired" | OAuth needs refresh | Ask Claude to "Authenticate with QuickBooks" |
| "Company not found" | Wrong company selected | Re-authenticate and select correct company |
| Tool not available | MCP not configured | Run `/shopify-qbo:setup` |

### 4. Credential Files

Check QBO credentials:
```bash
test -f ~/.quickbooks-mcp/credentials.json && echo "Found" || echo "Missing"
```

If found, check for token presence (without revealing values).

### 5. Last Sync

Check for recent audit reports:
```bash
ls -t sync_output/sync_audit_*.json 2>/dev/null | head -1
```

If found, report the timestamp and summary stats.

## Status Report Format

Present results as a clear summary:

```
Shopify -> QBO Sync Status
--------------------------
Shopify MCP:    [connected|disconnected|not configured]
  Store:        your-store.myshopify.com
  Auth:         static token / OAuth

QBO MCP:        [connected|disconnected|not configured]
  Company:      Company Name
  Environment:  sandbox / production
  Tokens:       valid / expired / missing

Last sync:      2026-03-14 03:00:29 UTC
  Customers:    42 synced
  Invoices:     128 synced
  Tax match:    $1,234.56 (0 discrepancies)

Pipeline:       Ready / Needs attention
```
