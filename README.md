# Shopify → QuickBooks Online Sync Pipeline

An agentic, MCP-intermediated pipeline for one-way sync of customers, invoices, and tax data from Shopify to QuickBooks Online.

## Architecture

```
┌──────────────────┐     ┌─────────────────────────────┐     ┌──────────────────┐
│  Shopify Store   │     │     Claude Agent + Skill     │     │  QuickBooks      │
│                  │     │                               │     │  Online          │
│  ┌────────────┐  │     │  ┌─────────────────────────┐ │     │  ┌────────────┐  │
│  │ Customers  │──┼──┐  │  │ 1. Extract (Shopify MCP)│ │  ┌──┼──│ Customers  │  │
│  │ Orders     │  │  │  │  │ 2. Transform (Scripts)  │ │  │  │  │ Invoices   │  │
│  │ Tax Lines  │  │  │  │  │ 3. Load (QBO MCP)       │ │  │  │  │ Tax Codes  │  │
│  └────────────┘  │  │  │  │ 4. Validate (Scripts)   │ │  │  │  └────────────┘  │
│                  │  │  │  └─────────────────────────┘ │  │  │                  │
└──────────────────┘  │  │                               │  │  └──────────────────┘
                      │  │  Skill Plugin: SKILL.md       │  │
                      │  │  orchestrates the workflow     │  │
                      │  └─────────────────────────────┘  │
                      │         │              │           │
                      │    ┌────┴────┐    ┌────┴────┐     │
                      └───▶│Shopify  │    │  QBO    │─────┘
                           │  MCP    │    │  MCP    │
                           └─────────┘    └─────────┘
                         GeLi2001/        laf-rge/
                         shopify-mcp      quickbooks-mcp
```

## Components

### MCP Servers (Connectors)

| Component | Repo | Role |
|-----------|------|------|
| **Shopify MCP** | [GeLi2001/shopify-mcp](https://github.com/GeLi2001/shopify-mcp) | Read customers, orders, tax data from Shopify Admin API |
| **QBO MCP** | [laf-rge/quickbooks-mcp](https://github.com/laf-rge/quickbooks-mcp) | Write customers, invoices, query QBO data |

### Skill Plugin (Orchestrator)

| File | Purpose |
|------|---------|
| `SKILL.md` | Main skill definition -- triggers, workflow, mapping rules |
| `mcp-servers.md` | MCP server setup and configuration guide |
| `field-mapping.md` | Complete Shopify -> QBO field mapping spec |
| `tax-mapping.json` | Configurable tax code mapping |
| `agent-playbook.md` | Step-by-step MCP tool call reference |

### Scripts (Transform Layer)

| Script | Purpose |
|--------|---------|
| `transform_customers.py` | Shopify customer JSON -> QBO customer JSON |
| `transform_invoices.py` | Shopify order JSON -> QBO invoice JSON with tax |
| `orchestrator.py` | Runs full transform + validate pipeline |

## Quick Start

### 1. Install MCP Servers

```bash
# Shopify MCP (via npx, no install needed)
# Just need your Shopify access token + domain

# QBO MCP
git clone https://github.com/laf-rge/quickbooks-mcp.git
cd quickbooks-mcp && npm install && npm run build
```

### 2. Configure Claude Desktop / Claude Code

Add to your MCP config (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "shopify": {
      "command": "npx",
      "args": ["shopify-mcp", "--accessToken", "<TOKEN>", "--domain", "<SHOP>.myshopify.com"]
    },
    "quickbooks": {
      "command": "node",
      "args": ["/path/to/quickbooks-mcp/dist/index.js"]
    }
  }
}
```

### 3. Install the Skill

Copy this directory to your Claude skills directory:
```bash
cp -r ShopifyQuickbooksBridge/ ~/.claude/skills/shopify-qbo-sync/
# Or for Claude Code project-level:
cp -r ShopifyQuickbooksBridge/ <project>/.claude/skills/shopify-qbo-sync/
```

### 4. Run the Sync

Ask Claude:
> "Sync my Shopify customers and orders to QuickBooks Online"

The agent will:
1. Pull customers and orders from Shopify via MCP
2. Run the transform scripts to map fields and taxes
3. Upsert customers into QBO via MCP
4. Create invoices in QBO via MCP (draft mode)
5. Validate tax totals and generate an audit report

## Customization

### Tax Mapping
Edit `tax-mapping.json` to match your jurisdiction:
- Add your state/province tax titles
- Set specific QBO tax rate IDs if auto-detection fails
- Configure defaults for unknown tax codes

### Field Mapping
Modify `field-mapping.md` and the transform scripts if you need:
- Custom customer fields (e.g., Shopify metafields → QBO custom fields)
- Different invoice numbering scheme
- Alternative item/product resolution in QBO

### Order Filtering
By default, only `paid` orders are synced. Change via:
- `--status-filter all` for all orders
- `--status-filter partially_refunded` for partially refunded

## Entities Synced

| Entity | Shopify Source | QBO Target | Dedup Key |
|--------|---------------|------------|-----------|
| Customers | Admin API `/customers` | Customer | Email |
| Orders → Invoices | Admin API `/orders` | Invoice | DocNumber (SH-{order#}) |
| Tax Lines | Per-order `taxLines[]` | TxnTaxDetail | N/A (per invoice) |

## Safety Features

- **Draft mode**: QBO MCP creates invoices in draft by default
- **Deduplication**: Checks for existing records before creating
- **Validation**: Cross-checks tax totals between source and target
- **Audit trail**: Every sync generates a timestamped audit report
- **Error resilience**: Single record failures don't abort the batch
