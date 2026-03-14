# Field Mapping Reference: Shopify → QuickBooks Online

## Customer Mapping

### Core Fields
```json
{
  "shopify_customer": {
    "id": "gid://shopify/Customer/123",
    "firstName": "Jane",
    "lastName": "Smith",
    "email": "jane@example.com",
    "phone": "+1-555-0100",
    "taxExempt": false,
    "tags": ["wholesale", "vip"],
    "defaultAddress": {
      "address1": "123 Main St",
      "address2": "Suite 4",
      "city": "Seattle",
      "province": "Washington",
      "provinceCode": "WA",
      "zip": "98101",
      "country": "United States",
      "countryCodeV2": "US"
    }
  },
  "qbo_customer": {
    "DisplayName": "Jane Smith",
    "GivenName": "Jane",
    "FamilyName": "Smith",
    "PrimaryEmailAddr": { "Address": "jane@example.com" },
    "PrimaryPhone": { "FreeFormNumber": "+1-555-0100" },
    "Taxable": true,
    "BillAddr": {
      "Line1": "123 Main St",
      "Line2": "Suite 4",
      "City": "Seattle",
      "CountrySubDivisionCode": "WA",
      "PostalCode": "98101",
      "Country": "US"
    },
    "Notes": "Shopify tags: wholesale, vip"
  }
}
```

### Mapping Rules
- `DisplayName` = `firstName` + " " + `lastName` (must be unique in QBO)
- `Taxable` = inverse of `taxExempt` 
- If DisplayName collision in QBO, append email: "Jane Smith (jane@example.com)"
- Shopify `tags` → QBO `Notes` field (comma-separated)
- Shopify `id` → store as QBO custom field or note for cross-reference

## Invoice Mapping (from Shopify Order)

### Core Structure
```json
{
  "shopify_order": {
    "id": "gid://shopify/Order/456",
    "name": "#1001",
    "createdAt": "2025-03-15T10:30:00Z",
    "customer": { "email": "jane@example.com" },
    "lineItems": [
      {
        "title": "Premium Widget",
        "quantity": 2,
        "originalUnitPrice": "29.99",
        "totalDiscount": "5.00",
        "taxLines": [
          { "title": "WA State Tax", "rate": 0.065, "price": "3.57" }
        ]
      }
    ],
    "totalTax": "3.57",
    "totalPrice": "58.55",
    "totalDiscounts": "5.00",
    "shippingLines": [
      { "title": "Standard Shipping", "price": "5.99" }
    ],
    "taxLines": [
      { "title": "WA State Tax", "rate": 0.065, "price": "3.57" }
    ]
  },
  "qbo_invoice": {
    "DocNumber": "SH-1001",
    "TxnDate": "2025-03-15",
    "CustomerRef": { "value": "<QBO_CUSTOMER_ID>" },
    "Line": [
      {
        "DetailType": "SalesItemLineDetail",
        "Amount": 59.98,
        "Description": "Premium Widget",
        "SalesItemLineDetail": {
          "ItemRef": { "value": "<QBO_ITEM_ID>", "name": "Sales" },
          "Qty": 2,
          "UnitPrice": 29.99,
          "TaxCodeRef": { "value": "TAX" }
        }
      },
      {
        "DetailType": "SalesItemLineDetail",
        "Amount": 5.99,
        "Description": "Standard Shipping",
        "SalesItemLineDetail": {
          "ItemRef": { "value": "<SHIPPING_ITEM_ID>", "name": "Shipping" },
          "Qty": 1,
          "UnitPrice": 5.99,
          "TaxCodeRef": { "value": "NON" }
        }
      },
      {
        "DetailType": "DiscountLineDetail",
        "Amount": 5.00,
        "DiscountLineDetail": {
          "PercentBased": false,
          "DiscountPercent": null
        }
      }
    ],
    "TxnTaxDetail": {
      "TotalTax": 3.57,
      "TaxLine": [
        {
          "Amount": 3.57,
          "DetailType": "TaxLineDetail",
          "TaxLineDetail": {
            "TaxRateRef": { "value": "<QBO_TAX_RATE_ID>" },
            "PercentBased": true,
            "TaxPercent": 6.5,
            "NetAmountTaxable": 54.98
          }
        }
      ]
    }
  }
}
```

### Invoice Mapping Rules
- `DocNumber` = "SH-" + Shopify order `name` (stripped of #)
- `TxnDate` = `createdAt` truncated to YYYY-MM-DD
- `CustomerRef` = look up QBO customer by Shopify customer email
- Line items: one QBO Line per Shopify lineItem
  - `Amount` = `quantity` × `originalUnitPrice`
  - Discount applied as separate DiscountLineDetail
- Shipping: separate line item with NON tax code
- Tax: aggregate Shopify `taxLines` into QBO `TxnTaxDetail`
  - Map tax title → QBO TaxCode via tax-mapping.json
  - Convert Shopify decimal rate (0.065) → QBO percent (6.5)

## Tax Mapping

### Default Mappings (US)
See `tax-mapping.json` for the full configurable map.

### Tax Rate Conversion
- Shopify stores tax rate as decimal: `0.065` = 6.5%
- QBO stores tax percent as number: `6.5`
- Conversion: `qbo_percent = shopify_rate × 100`

### Tax Exemption
- If Shopify customer `taxExempt = true`:
  - QBO customer `Taxable = false`
  - All invoice lines for this customer use `TaxCodeRef: "NON"`

### Multi-jurisdiction Tax
- Shopify may have multiple taxLines per order (state + county + city)
- QBO handles this via composite tax codes
- The transform script groups by jurisdiction and maps to QBO tax rate IDs
- If a jurisdiction can't be mapped, flag for manual review

## Deduplication Strategy

### Customers
- **Primary key**: email address
- **Query**: `SELECT * FROM Customer WHERE PrimaryEmailAddr = '{email}'`
- **If found**: compare fields, update if changed, skip if identical
- **If not found**: create new

### Invoices
- **Primary key**: DocNumber (= "SH-" + order number)
- **Query**: `SELECT * FROM Invoice WHERE DocNumber = 'SH-{order_number}'`
- **If found**: skip (orders are immutable in Shopify)
- **If not found**: create new

## Edge Cases

1. **Guest checkouts**: Shopify orders without customer accounts
   - Create QBO customer from order's billing email + name
   - Tag as "Shopify Guest" in QBO Notes

2. **Refunds**: Not handled in initial sync (one-way, forward only)
   - Can be added as Credit Memos in a future phase

3. **Multi-currency**: If Shopify order currency ≠ QBO home currency
   - Store original currency in QBO memo field
   - Use QBO's exchange rate for the transaction date
   - Flag for review if rate differential > 2%

4. **Free orders ($0)**: Include in sync with $0 invoice
   - Useful for tracking promotional orders

5. **Draft/Unpaid orders**: Filter by `financial_status` in Shopify
   - Default: only sync `paid` and `partially_refunded` orders
