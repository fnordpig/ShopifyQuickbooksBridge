# MCP Server Setup Reference

## Recommended Configuration

### 1. Shopify MCP: GeLi2001/shopify-mcp

**Why this one**: Most mature community Shopify Admin API server (81+ stars), supports
full CRUD on products/customers/orders via GraphQL, handles both OAuth and static tokens,
NPX-runnable with zero local setup.

#### Prerequisites
- Node.js 18+
- A Shopify Custom App with Admin API access

#### Create Shopify Custom App
1. Go to Shopify Admin → Settings → Apps and sales channels
2. Click "Develop apps" (enable developer preview if needed)
3. Click "Create an app" → name it (e.g., "QBO Sync MCP")
4. Configure Admin API scopes:
   - `read_customers`
   - `read_orders`
   - `read_products`
   - `read_inventory`
5. Install the app → copy the Admin API access token

#### Option A: Static Access Token (existing apps before Jan 2026)
```json
{
  "mcpServers": {
    "shopify": {
      "command": "npx",
      "args": [
        "shopify-mcp",
        "--accessToken", "<YOUR_SHOPIFY_ACCESS_TOKEN>",
        "--domain", "<YOUR_SHOP>.myshopify.com"
      ]
    }
  }
}
```

#### Option B: OAuth Client Credentials (new apps after Jan 2026)
```json
{
  "mcpServers": {
    "shopify": {
      "command": "npx",
      "args": [
        "shopify-mcp",
        "--clientId", "<YOUR_CLIENT_ID>",
        "--clientSecret", "<YOUR_CLIENT_SECRET>",
        "--domain", "<YOUR_SHOP>.myshopify.com"
      ]
    }
  }
}
```

#### Available Tools
| Tool                 | Description                                    |
|----------------------|------------------------------------------------|
| `get-products`       | List/search products with variants             |
| `get-customers`      | List all customers, search by name/email       |
| `get-orders`         | List orders with status/date filters           |
| `get-order`          | Get single order by ID with full detail        |
| `get-customer-orders`| Orders for a specific customer                 |
| `update-customer`    | Update customer fields including tax exemption  |

---

### 2. QBO MCP: laf-rge/quickbooks-mcp

**Why this one**: Designed for financial professionals, auto-resolves entity names
(no internal ID lookups needed), has report tools, SQL-like query across all entities,
safe draft mode by default, production-ready OAuth management.

#### Prerequisites  
- Node.js 18+
- A QuickBooks Online developer account with OAuth2 app

#### Create QBO OAuth App
1. Go to https://developer.intuit.com → create an app
2. Select QuickBooks Online scopes: `com.intuit.quickbooks.accounting`
3. Set redirect URI (e.g., `https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl`)
4. Copy Client ID and Client Secret

#### Setup
```bash
git clone https://github.com/laf-rge/quickbooks-mcp.git
cd quickbooks-mcp
npm install
npm run build
```

#### Credentials (Local Mode)
Create `~/.quickbooks-mcp/credentials.json`:
```json
{
  "client_id": "<YOUR_CLIENT_ID>",
  "client_secret": "<YOUR_CLIENT_SECRET>",
  "access_token": "<FROM_OAUTH_FLOW>",
  "refresh_token": "<FROM_OAUTH_FLOW>",
  "redirect_url": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
}
```

Then run the `qbo_authenticate` tool to complete OAuth flow.

#### Claude Desktop / Claude Code Config
```json
{
  "mcpServers": {
    "quickbooks": {
      "command": "node",
      "args": ["/path/to/quickbooks-mcp/dist/index.js"]
    }
  }
}
```

#### Available Tools
| Tool                  | Description                                         |
|-----------------------|-----------------------------------------------------|
| `query`               | SQL-like query across any QBO entity                |
| `create_invoice`      | Create invoice (draft mode by default)              |
| `create_customer`     | Create customer with auto name resolution           |
| `create_bill`         | Create bill                                          |
| `create_journal_entry`| Create journal entry                                |
| `profit_and_loss`     | P&L report with date/department breakdown           |
| `balance_sheet`       | Balance sheet report                                 |
| `trial_balance`       | Trial balance report                                 |
| `delete_transaction`  | Delete any transaction type                          |

---

### Alternative QBO MCPs

#### intuit/quickbooks-online-mcp-server (Official)
- Pros: Official Intuit project, well-tested
- Cons: Requires internal QBO IDs for everything, no report tools
- Best for: Developers already familiar with QBO API internals

#### vespo92/QBOMCP
- Pros: Natural language friendly, smart date parsing, helpful suggestions
- Cons: Newer/less mature (0 stars), single commit
- Best for: Accountants who want conversational interaction

---

## Combined Config (Both MCPs)

For Claude Desktop or Claude Code, combine both servers:

```json
{
  "mcpServers": {
    "shopify": {
      "command": "npx",
      "args": [
        "shopify-mcp",
        "--accessToken", "<SHOPIFY_TOKEN>",
        "--domain", "<SHOP>.myshopify.com"
      ]
    },
    "quickbooks": {
      "command": "node",
      "args": ["/path/to/quickbooks-mcp/dist/index.js"]
    }
  }
}
```

## Security Notes

- Never commit tokens to version control
- Use environment variables or credential files outside the repo
- Shopify tokens grant full Admin API access — scope appropriately
- QBO refresh tokens auto-rotate; the MCP handles this
- Consider using QBO sandbox environment for initial testing
