# Shopify Custom App Creation Walkthrough

Step-by-step guide for creating a Shopify custom app to get API credentials for the sync pipeline.

## Prerequisites

- A Shopify store with admin access (store owner or staff with "Apps" permission)
- Your store URL: `your-store.myshopify.com`

## Step 1: Open App Settings

1. Log into your Shopify Admin at `https://your-store.myshopify.com/admin`
2. Look at the bottom-left corner of the sidebar
3. Click the **gear icon** (Settings)
4. In the Settings menu, click **Apps and sales channels**

## Step 2: Enable Custom App Development

If this is your first custom app:

1. At the top of the Apps page, click **Develop apps**
2. You may see a banner: "Custom app development is disabled"
3. Click **Allow custom app development**
4. Read the warning, then click **Allow custom app development** again to confirm

This only needs to be done once per store. If you already see the "Create an app" button, skip this.

## Step 3: Create the App

1. Click **Create an app**
2. In the dialog:
   - **App name**: Enter "QBO Sync Agent" (or any name you prefer)
   - **App developer**: Select yourself or the appropriate developer account
3. Click **Create app**

You'll be taken to the app's overview page.

## Step 4: Configure API Scopes

The app needs read access to customers, orders, and products. No write access is needed for the source system.

1. Click the **Configuration** tab
2. Under "Admin API integration", click **Configure**
3. In the scopes list, search for and enable:

| Scope | Purpose |
|-------|---------|
| `read_customers` | Pull customer data for QBO sync |
| `read_orders` | Pull order data to create QBO invoices |
| `read_products` | Resolve product names for invoice line items |

4. Click **Save**

**Why read-only?** The sync pipeline only reads from Shopify and writes to QBO. Keeping Shopify scopes read-only follows the principle of least privilege and prevents accidental data modification.

## Step 5: Install the App

1. Click the **API credentials** tab
2. Click **Install app**
3. In the confirmation dialog, click **Install**

The app is now installed on your store.

## Step 6: Get Your Credentials

### For Legacy Apps (pre-January 2026)

After installing, you'll see an "Admin API access token" section:

1. Click **Reveal token once**
2. **Copy the token immediately** - it starts with `shpat_` and looks like:
   ```
   shpat_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
   ```
3. Save it somewhere secure (password manager, encrypted note)

**WARNING:** This token is shown exactly once. If you navigate away without copying it, you'll need to:
1. Uninstall the app (API credentials tab -> Uninstall)
2. Reinstall it (step 5 above)
3. Reveal the new token

### For New Apps (post-January 2026)

Shopify transitioned to OAuth client credentials for new apps:

1. On the **API credentials** tab, find:
   - **Client ID** - a long alphanumeric string
   - **Client secret** - click "Show" to reveal it
2. Copy both values

The MCP server handles the OAuth token exchange and refresh automatically. Tokens are valid for approximately 24 hours and auto-refresh.

### How to Tell Which Type You Have

- If you see "Admin API access token" with a "Reveal token once" button -> **Legacy (static token)**
- If you see "Client ID" and "Client secret" fields -> **OAuth (new app)**
- Some apps created during the transition period may show both

## Step 7: Note Your Store Domain

Your store domain is the `.myshopify.com` URL, not any custom domain you may have set up.

Find it by looking at your browser's address bar in Shopify Admin:
```
https://admin.shopify.com/store/YOUR-STORE-NAME
```

Your domain is: `YOUR-STORE-NAME.myshopify.com`

You can also find it in **Settings** -> **Domains**.

## Troubleshooting

### "You don't have permission to access this page"
You need the store owner or a staff member with the "Apps" permission to create custom apps.

### "Custom app development is disabled"
Follow Step 2 above. Only the store owner can enable this.

### "The app couldn't be installed"
This usually means there's a conflict with existing app installations. Try:
1. Check if you already have an app with the same name
2. Delete the existing one and create a new one

### Token issues
- **Token doesn't start with `shpat_`**: You may be looking at the API key, not the access token. The access token is under "Admin API access token", not "API key and secret key"
- **Token was already revealed**: Uninstall and reinstall the app to get a new token
- **"Unauthorized" errors**: The token may have been revoked. Check the app's status in Settings -> Apps

## Security Best Practices

- Never commit tokens to version control (add to `.gitignore`)
- Use environment variables or `.env` files for token storage
- Rotate tokens periodically by uninstalling/reinstalling the app
- Use the minimum required scopes (read-only for the source system)
- For team environments, use OAuth client credentials instead of static tokens
