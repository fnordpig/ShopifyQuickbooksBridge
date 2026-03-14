---
name: setup
description: >
  Interactive setup wizard for the Shopify to QuickBooks Online sync pipeline.
  Guides users through creating API credentials, configuring MCP servers, and verifying
  connections. Use whenever the user mentions "setup", "onboard", "configure", "get started",
  "connect shopify to quickbooks", "mcp setup", "create shopify app", "qbo credentials",
  or asks how to start using the Shopify-QBO sync. Also trigger when the user runs into
  connection errors with either MCP server and needs help troubleshooting.
---

# Shopify -> QBO Setup Wizard

Guide the user through the complete Shopify-QuickBooks Online sync pipeline setup.
This is interactive and step-by-step. Move at the user's pace and verify each step before advancing.

## Overview

| Phase | What | Time |
|-------|------|------|
| 0 | Prerequisites check | 30 sec |
| 1 | Create Shopify custom app | 3-5 min |
| 2 | Configure Shopify MCP server | 1-2 min |
| 3 | Create QBO developer app | 3-5 min |
| 4 | Install & configure QBO MCP server | 3-5 min |
| 5 | Verify full pipeline | 1-2 min |

Total: ~15 minutes for a fresh setup.

## Step 1: Launch Progress Tracker & Check Prerequisites

Generate the interactive progress page and open it:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/generate_progress.py \
  --output /tmp/shopify-qbo-setup.html --step 0
open /tmp/shopify-qbo-setup.html
```

Run the environment checker:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/check_env.py
```

This checks Node.js 18+, Python 3.10+, git, npx, Claude CLI, and detects existing MCP configs.
If anything is missing, provide install instructions. If MCP servers are already configured,
ask the user if they want to reconfigure or skip those phases.

Update the tracker after each phase:
```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/generate_progress.py \
  --output /tmp/shopify-qbo-setup.html --step <N>
```

## Step 2: Create Shopify Custom App

Read `${CLAUDE_PLUGIN_ROOT}/references/shopify-setup.md` for the full walkthrough.

Walk the user through:
1. Log into Shopify Admin -> Settings (gear icon, bottom-left) -> Apps and sales channels
2. Click **Develop apps** (enable custom app development if first time)
3. Create an app named "QBO Sync Agent"
4. Configuration tab -> Admin API integration -> Configure
5. Enable scopes: `read_customers`, `read_orders`, `read_products`
6. Save, then API credentials tab -> Install app

**Credential types:**
- **Legacy (pre-Jan 2026):** Static access token (`shpat_...`) - shown ONCE after install
- **OAuth (post-Jan 2026):** Client ID + Client Secret from API credentials tab

Collect: store domain + credentials. Confirm by showing first 8 chars only.

## Step 3: Configure Shopify MCP

```bash
# Static token
claude mcp add shopify -- npx shopify-mcp \
  --accessToken <TOKEN> --domain <STORE>.myshopify.com

# OAuth
claude mcp add shopify -- npx shopify-mcp \
  --clientId <ID> --clientSecret <SECRET> --domain <STORE>.myshopify.com
```

**Verify:** Use the Shopify MCP to list the first 3 products.

Common issues:
- "SHOPIFY_ACCESS_TOKEN not set" -> Use package `shopify-mcp`, not `shopify-mcp-server`
- "Unauthorized" -> Token wrong or expired
- "Not found" -> Domain format: `store-name.myshopify.com` (no https://)

## Step 4: Create QBO Developer App

Read `${CLAUDE_PLUGIN_ROOT}/references/qbo-setup.md` for the full walkthrough.

Walk the user through:
1. Go to https://developer.intuit.com -> sign in
2. Dashboard -> Create an app -> QuickBooks Online and Payments
3. Name it, enable scope `com.intuit.quickbooks.accounting`
4. Set Redirect URI: `https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl`
5. Copy Client ID and Client Secret from Keys & credentials -> Development tab

Recommend starting with Development/Sandbox credentials.

## Step 5: Install & Configure QBO MCP

```bash
git clone https://github.com/laf-rge/quickbooks-mcp.git ~/quickbooks-mcp
cd ~/quickbooks-mcp && npm install && npm run build
```

Create `~/.quickbooks-mcp/credentials.json`:
```json
{
  "client_id": "<QBO_CLIENT_ID>",
  "client_secret": "<QBO_CLIENT_SECRET>",
  "redirect_url": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
}
```

```bash
claude mcp add quickbooks -- node ~/quickbooks-mcp/dist/index.js
```

Complete OAuth: restart Claude Code, then "Authenticate with QuickBooks".
Auth codes expire quickly - user must complete browser authorization promptly.

**Verify:** Use the QBO MCP to query `SELECT COUNT(*) FROM Customer`.

## Step 6: Verify & Test

Run a small end-to-end test:
1. Pull 3 customers and 3 orders from Shopify via MCP
2. Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py` in transform-only mode
3. Review transformed output and audit report
4. Optionally load 1 test record into QBO sandbox

Update progress tracker to step 6 (all complete).

Tell the user: "You're all set. Use `/shopify-qbo:sync` to run your first sync."
