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

# Shopify → QBO Setup Wizard

Guide the user through connecting Shopify and QuickBooks Online. This is interactive —
move at the user's pace, explain each step in plain language, and verify before advancing.

## Overview

| Step | What you'll do | Time |
|------|---------------|------|
| 1 | Check your computer has the right tools installed | 30 sec |
| 2 | Create a Shopify app to allow reading your store data | 3–5 min |
| 3 | Connect Claude to your Shopify store | 1–2 min |
| 4 | Create a QuickBooks developer app | 3–5 min |
| 5 | Connect Claude to your QuickBooks account | 3–5 min |
| 6 | Test that everything works | 1–2 min |

Total: about 15 minutes.

## Step 1: Check Prerequisites

Run the environment checker:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/check_env.py
```

This checks that Node.js and Python are installed. If anything is missing, help the user
install it before continuing.

Also generate the interactive progress page:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/generate_progress.py \
  --output /tmp/shopify-qbo-setup.html --step 0
open /tmp/shopify-qbo-setup.html
```

Update the progress tracker after each step:
```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/generate_progress.py \
  --output /tmp/shopify-qbo-setup.html --step <N>
```

## Step 2: Create a Shopify App

Tell the user:

> We need to create a small app inside your Shopify store that gives Claude
> permission to read your customers and orders. It's read-only — it can't
> change anything in your store.

### Instructions to give the user:

1. **Open your Shopify app settings.** Go to:
   `https://YOUR-STORE.myshopify.com/admin/settings/apps/development`
   (Replace YOUR-STORE with your actual store name)

   Or navigate there manually: Shopify Admin → Settings (gear icon, bottom-left) → Apps and sales channels → Develop apps

2. **If you see "Custom app development is disabled"**, click **Allow custom app development** and confirm. This is a one-time step.

3. **Click "Create an app"**. Name it **QBO Sync Agent** (or anything you like).

4. **Set permissions.** Go to the Configuration tab, click **Configure** under Admin API integration, and turn on these three:
   - `read_customers`
   - `read_orders`
   - `read_products`

   Then click **Save**.

5. **Install the app.** Go to the API credentials tab and click **Install app**, then **Install** to confirm.

6. **Copy your credentials:**

   - **If you see "Reveal token once"** (older stores): Click it and **copy the token immediately**. It starts with `shpat_` and looks like `shpat_a1b2c3d4...`. You only get to see it once — if you lose it, you'll need to uninstall and reinstall the app.

   - **If you see "Client ID" and "Client secret"** (newer stores): Copy both values. These can be viewed again later.

7. **Note your store domain.** It's the `your-store.myshopify.com` part of your admin URL (not any custom domain you may use).

Ask the user to share: their store domain and which credential type they have (token or client ID/secret). Confirm by showing only the first 8 characters.

## Step 3: Connect Claude to Shopify

Based on what the user has:

**If they have an access token (starts with `shpat_`):**
```bash
claude mcp add shopify -- npx shopify-mcp \
  --accessToken <TOKEN> --domain <STORE>.myshopify.com
```

**If they have Client ID + Client Secret:**
```bash
claude mcp add shopify -- npx shopify-mcp \
  --clientId <CLIENT_ID> --clientSecret <CLIENT_SECRET> --domain <STORE>.myshopify.com
```

**Test the connection** by listing 3 products from their store using the Shopify MCP `get-products` tool.

If it works, tell the user: "Your Shopify connection is working. I can see your products."

**If it fails:**
- "SHOPIFY_ACCESS_TOKEN not set" → Make sure the package is `shopify-mcp` (not `shopify-mcp-server`)
- "Unauthorized" → The token or credentials are wrong. Double-check them.
- "Not found" → The domain format should be `store-name.myshopify.com` (no `https://`)

## Step 4: Create a QuickBooks Developer App

Tell the user:

> Now we'll create an app on Intuit's developer portal that lets Claude
> read and write to your QuickBooks account. We'll start with sandbox mode
> so nothing touches your real books until you're ready.

### Instructions to give the user:

1. **Open the Intuit developer portal:**
   https://developer.intuit.com/app/developer/dashboard

   Sign in with the same account you use for QuickBooks. If you don't have a developer account, click **Create an account** — it's free and takes 30 seconds.

2. **Click "Create an app"** (blue button on the dashboard).

3. **Fill in the form:**
   - Platform: **QuickBooks Online and Payments**
   - App name: **Shopify Sync Agent** (or anything you like)
   - Scopes: Check **com.intuit.quickbooks.accounting** only

4. **Add the redirect URL.** On the app settings page, find **Redirect URIs** and add:
   ```
   https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl
   ```
   Then click **Save**.

5. **Copy your credentials.** Go to **Keys & credentials** and select the **Development** tab:
   - **Client ID**: copy this value
   - **Client Secret**: click "Show", then copy

> **Why "Development"?** Development mode connects to a sandbox with fake data.
> This lets you test safely. When you're ready to use real data, you'll switch
> to the Production tab and copy those credentials instead.

Ask the user to share their Client ID and Client Secret. Confirm by showing the first 8 characters only.

## Step 5: Connect Claude to QuickBooks

This requires installing a small program and then authorizing it with your QuickBooks account.

### Install the QBO connector:

```bash
git clone https://github.com/laf-rge/quickbooks-mcp.git ~/quickbooks-mcp
cd ~/quickbooks-mcp && npm install && npm run build
```

### Save your credentials:

```bash
mkdir -p ~/.quickbooks-mcp
```

Create `~/.quickbooks-mcp/credentials.json` with the user's credentials:

```json
{
  "client_id": "<their Client ID>",
  "client_secret": "<their Client Secret>",
  "redirect_url": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
}
```

### Connect to Claude:

```bash
claude mcp add quickbooks -- node ~/quickbooks-mcp/dist/index.js
```

### Authorize with QuickBooks:

Tell the user:

> I'm going to open a browser window where you'll sign into QuickBooks and
> give this app permission to access your account. When you see the Intuit
> screen, select your company and click **Connect**. The browser will redirect
> to a page — that's normal, the connection will complete automatically.
>
> **Important:** This needs to happen within a couple of minutes or the
> authorization will expire.

Restart Claude Code, then use the QBO MCP `qbo_authenticate` tool to start the OAuth flow.

**Test the connection** by querying: `SELECT COUNT(*) FROM Customer`

If it works, tell the user: "Your QuickBooks connection is working. I can see your data."

**If it fails:**
- "Invalid client" → Client ID or Secret is wrong. Double-check against the Development tab at https://developer.intuit.com/app/developer/dashboard
- "Redirect URI mismatch" → The redirect URL must be exactly `https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl` — check for typos
- Browser doesn't open → The user may be in a remote/SSH session. Try opening the authorization URL manually.

## Step 6: Test Everything

Run a small end-to-end test:

1. Pull 3 customers and 3 orders from Shopify via MCP
2. Run the transform in preview mode:
   ```bash
   python ${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py \
     --shopify-customers /tmp/test_customers.json \
     --shopify-orders /tmp/test_orders.json \
     --tax-map ${CLAUDE_PLUGIN_ROOT}/tax-mapping.json \
     --output-dir /tmp/test_output \
     --mode transform-only
   ```
3. Show the user what the transformed data looks like
4. Optionally load 1 test record into QBO (in draft mode)

Update the progress tracker to the final step.

Tell the user:

> **You're all set!** Here's what you can do now:
>
> - `/shopify-qbo:sync` — run your first sync
> - `/shopify-qbo:status` — check connection health anytime
> - `/shopify-qbo:report` — see what's synced
>
> I recommend starting with a sync of just a few records to make sure
> tax mappings look right, then doing a full sync.
