# ShopifyQuickbooksBridge

Claude plugin for one-way sync of customers and orders from Shopify to QuickBooks Online via MCP servers.

## Plugin Structure

```
shopify-qbo/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── commands/                    # Slash commands (thin wrappers)
│   ├── setup.md                 # /shopify-qbo:setup
│   ├── configure.md             # /shopify-qbo:configure
│   ├── sync.md                  # /shopify-qbo:sync
│   ├── reconcile.md             # /shopify-qbo:reconcile
│   └── status.md                # /shopify-qbo:status
├── skills/                      # Full skill definitions
│   ├── setup/SKILL.md           # Interactive onboarding wizard
│   ├── configure/SKILL.md       # Credential & MCP management
│   ├── sync/SKILL.md            # Four-phase sync pipeline
│   ├── reconcile/SKILL.md       # Tax reconciliation & audit
│   └── status/SKILL.md          # Connection health check
├── scripts/                     # Python transform & utility scripts
│   ├── transform_customers.py   # Shopify customer -> QBO customer
│   ├── transform_invoices.py    # Shopify order -> QBO invoice + tax
│   ├── orchestrator.py          # Full pipeline: transform -> validate -> report
│   ├── check_env.py             # Prerequisite checker
│   └── generate_progress.py     # Interactive HTML setup wizard
├── references/                  # Documentation loaded on demand
│   ├── field-mapping.md         # Shopify -> QBO field mapping spec
│   ├── mcp-servers.md           # MCP server setup guide
│   ├── shopify-setup.md         # Shopify custom app walkthrough
│   └── qbo-setup.md             # QBO developer app walkthrough
├── tax-mapping.json             # Configurable tax code mapping
├── DESIGN.md                    # Implementation design document
└── tests/
    ├── test_transform_customers.py
    ├── test_transform_invoices.py
    └── test_orchestrator.py
```

## Commands

| Command | Purpose |
|---------|---------|
| `/shopify-qbo:setup` | Interactive setup wizard (prerequisites, app creation, MCP config, verification) |
| `/shopify-qbo:configure` | Manage credentials, rotate tokens, switch sandbox/production |
| `/shopify-qbo:sync` | Run the four-phase sync pipeline (extract, transform, load, validate) |
| `/shopify-qbo:reconcile` | Tax reconciliation and audit reporting |
| `/shopify-qbo:status` | Check MCP connection health and configuration status |

## Running Scripts Directly

```bash
python scripts/transform_customers.py --input shopify_customers.json --output qbo_customers.json --pretty
python scripts/transform_invoices.py --input shopify_orders.json --output qbo_invoices.json --tax-map tax-mapping.json --pretty
python scripts/orchestrator.py --shopify-customers shopify_customers.json --shopify-orders shopify_orders.json --tax-map tax-mapping.json --output-dir sync_output --mode transform-only
```

## Running Tests

```bash
python3 -m unittest tests/test_transform_customers tests/test_transform_invoices tests/test_orchestrator -v
```

## Dependencies

Python 3.10+ (stdlib only, no pip packages). MCP servers require Node.js 18+.
