---
name: configure
description: >
  Manage Shopify and QBO API credentials and MCP server configuration.
  Use when tokens expire, credentials need rotating, switching between sandbox
  and production, or reconfiguring MCP server connections. Also use when the user
  says "update credentials", "rotate token", "switch to production", "change store",
  or needs to re-authenticate with either service.
---

# Configure Credentials & MCP Servers

Manage API credentials and MCP server configuration for the Shopify-QBO sync pipeline.

## Detect Current State

Start by checking what's configured:

```bash
claude mcp list 2>/dev/null
python ${CLAUDE_PLUGIN_ROOT}/scripts/check_env.py
```

Report what's found and ask what the user wants to change.

## Shopify Configuration

### Update Access Token

```bash
claude mcp remove shopify
claude mcp add shopify -- npx shopify-mcp \
  --accessToken <NEW_TOKEN> --domain <STORE>.myshopify.com
```

### Switch Store Domain

Same as above but with the new domain.

### Switch from Static Token to OAuth

```bash
claude mcp remove shopify
claude mcp add shopify -- npx shopify-mcp \
  --clientId <CLIENT_ID> --clientSecret <CLIENT_SECRET> \
  --domain <STORE>.myshopify.com
```

### Verify After Change

Use the Shopify MCP to list the first 3 products. If it works, the new config is good.

## QBO Configuration

### Re-authenticate (Token Expired)

Just ask Claude to "Authenticate with QuickBooks" - the MCP server handles the OAuth refresh.

### Update Client Credentials

Edit `~/.quickbooks-mcp/credentials.json`:
```json
{
  "client_id": "<NEW_CLIENT_ID>",
  "client_secret": "<NEW_CLIENT_SECRET>",
  "redirect_url": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
}
```

Remove `access_token` and `refresh_token` fields if present, then re-authenticate.

### Switch from Sandbox to Production

1. Go to https://developer.intuit.com -> your app -> Keys & credentials
2. Click the **Production** tab
3. Copy the Production Client ID and Client Secret
4. Update `~/.quickbooks-mcp/credentials.json` with production credentials
5. Remove existing tokens from the file
6. Restart Claude Code
7. Re-authenticate: "Authenticate with QuickBooks"
8. Select your production company when prompted

**Warning:** Production mode writes to real books. All creates default to draft mode, but confirm
the user understands the implications.

### Switch to AWS Secrets Manager (Production)

For shared or production environments:

```bash
aws secretsmanager create-secret --name prod/qbo \
  --secret-string '{"client_id":"...","client_secret":"...","access_token":"...","refresh_token":"...","redirect_url":"..."}'

aws ssm put-parameter --name /prod/qbo/company_id \
  --value "COMPANY_ID" --type SecureString
```

Create `.env` in the quickbooks-mcp directory:
```
QBO_CREDENTIAL_MODE=aws
AWS_REGION=us-east-2
QBO_SECRET_NAME=prod/qbo
QBO_COMPANY_ID_PARAM=/prod/qbo/company_id
```

### Verify After Change

Use the QBO MCP to query `SELECT COUNT(*) FROM Customer`.

## Tax Mapping Configuration

Edit `${CLAUDE_PLUGIN_ROOT}/tax-mapping.json` to customize tax code mappings for the user's jurisdiction.

To find QBO tax rate IDs, query: `SELECT Id, Name, RateValue FROM TaxRate`

See DESIGN.md Appendix B for full customization guide.
