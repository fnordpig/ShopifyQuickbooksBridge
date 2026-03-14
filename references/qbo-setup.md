# QuickBooks Online Developer App Creation Walkthrough

Step-by-step guide for creating a QBO developer app to get OAuth credentials for the sync pipeline.

## Prerequisites

- A QuickBooks Online account (any tier: Simple Start, Essentials, Plus, Advanced)
- An Intuit developer account (free, created in Step 1 if you don't have one)

## Step 1: Access the Developer Portal

1. Go to **https://developer.intuit.com**
2. Click **Sign in** in the top-right corner
3. Sign in with your Intuit account
   - This is the same account you use for QuickBooks, TurboTax, or Mint
   - If you don't have one, click **Create an account**

## Step 2: Create the App

1. Once signed in, click **Dashboard** in the top navigation bar
2. Click the **Create an app** button (blue button, usually center of page)
3. You'll see a form:
   - **Select a platform**: Choose **QuickBooks Online and Payments**
   - **App name**: Enter "Shopify Sync Agent" (or any name you prefer)
   - **Scopes**: Check **com.intuit.quickbooks.accounting**
     - This is the only scope needed. Do NOT enable Payments unless you specifically need it
4. Click **Create app**

## Step 3: Configure Redirect URI

After creating the app, you'll land on the app's settings page.

1. Find the **Redirect URIs** section
2. Add this exact URL:
   ```
   https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl
   ```
3. Click **Save**

This redirect URI is used by the QBO MCP server's built-in OAuth flow. When you authorize the app, Intuit redirects back to this URL, and the MCP server captures the authorization code.

## Step 4: Get Your Credentials

1. On the app's page, look for **Keys & credentials** (or it might be in the left sidebar)
2. You'll see two tabs: **Development** and **Production**
3. Start with the **Development** tab (sandbox mode)

Copy these two values:
- **Client ID**: A long string like `ABc123DEf456GHi789JKl012MNoPQrSTUvwXYZ`
- **Client Secret**: Click "Show" to reveal, then copy it

**NOTE:** The Client Secret can be regenerated if lost, but doing so invalidates the old one and requires re-authentication.

## Understanding Development vs Production

| Aspect | Development (Sandbox) | Production |
|--------|----------------------|------------|
| Data | Fake sandbox data | Your real QuickBooks data |
| Risk | Zero - can't affect real books | Real - changes are permanent |
| When to use | Initial setup, testing | After testing is complete |
| Rate limits | Same as production | 500 req/min |
| Token behavior | Same as production | Same |

**Recommendation:** Always start with Development. Switch to Production only after you've:
1. Successfully connected and tested the pipeline
2. Reviewed transformed data in the sandbox
3. Confirmed tax mappings are correct for your jurisdiction

### Switching to Production

When ready:
1. Go to your app's **Keys & credentials** page
2. Click the **Production** tab
3. Copy the Production Client ID and Client Secret
4. Update `~/.quickbooks-mcp/credentials.json` with the new values
5. Re-authenticate (the OAuth flow will connect to your real QBO company)

## Step 5: The OAuth Authentication Flow

After configuring the MCP server (see main setup guide), you'll need to complete the OAuth handshake:

1. The MCP server's `qbo_authenticate` tool opens a browser window
2. You see the Intuit consent screen showing:
   - Your app name ("Shopify Sync Agent")
   - The requested permissions (Accounting)
   - Which QuickBooks company to connect
3. Select your company and click **Connect**
4. The browser redirects to the OAuth playground URL
5. The MCP server captures the authorization code and exchanges it for tokens
6. Tokens are saved to `~/.quickbooks-mcp/credentials.json`

### Token Lifecycle

| Token | Validity | Renewal |
|-------|----------|---------|
| Access token | ~1 hour | Auto-refreshed by MCP server on each request |
| Refresh token | ~100 days | Renewed automatically when used |

The MCP server handles all token management. You only need to re-authenticate if:
- You don't use the connection for >100 days (refresh token expires)
- You regenerate the Client Secret
- You switch between Development and Production

## Troubleshooting

### "App not found" or "Invalid client"
- Double-check the Client ID and Client Secret in `credentials.json`
- Make sure you're using credentials from the correct tab (Development vs Production)
- The Client Secret may have been regenerated - copy the current one

### "Redirect URI mismatch"
The redirect URI in your app settings must exactly match:
```
https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl
```
Check for trailing slashes, typos, or http vs https.

### "Access denied" or scope errors
- Ensure `com.intuit.quickbooks.accounting` is enabled in your app's scopes
- If you changed scopes after the initial auth, you need to re-authenticate

### "Company not found" after authenticating
- During the OAuth consent screen, make sure you selected the correct QuickBooks company
- If you have multiple companies, you can only connect to one at a time
- Re-authenticate and select the correct company

### Browser doesn't open during authentication
- Make sure you're running Claude Code locally (not in a remote/SSH session)
- Try opening the authorization URL manually if Claude provides it
- Check if a popup blocker is preventing the window

### Token refresh failures
- The refresh token may have expired (>100 days of inactivity)
- Re-run the authentication flow: ask Claude "Authenticate with QuickBooks"
- Check that `credentials.json` is writable

## Security Best Practices

- Store credentials in `~/.quickbooks-mcp/credentials.json` (local) or AWS Secrets Manager (production)
- Never commit `credentials.json` to version control
- Use Development/Sandbox credentials for all testing
- The MCP server defaults to draft mode for all writes - review before committing
- Rotate the Client Secret periodically via the Intuit developer portal
- For production environments, use AWS Secrets Manager:
  ```
  QBO_CREDENTIAL_MODE=aws
  AWS_REGION=us-east-2
  QBO_SECRET_NAME=prod/qbo
  ```

## QBO API Quick Reference

Once connected, these are the key operations available through the MCP server:

| Tool | What it does |
|------|-------------|
| `query` | SQL-like queries: `SELECT * FROM Customer WHERE ...` |
| `create_customer` | Create customer with auto name resolution |
| `create_invoice` | Create invoice in draft mode |
| `profit_and_loss` | P&L report for tax reconciliation |
| `qbo_company_info` | Verify connection and company details |
| `qbo_authenticate` | Re-run OAuth flow |
