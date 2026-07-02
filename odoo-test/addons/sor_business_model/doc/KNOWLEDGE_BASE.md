# sor_business_model — Knowledge Base

## Overview

`sor_business_model` is a horizontal SOR module that records an organisation's **business model** at the company level and provides a rule-based mechanism for suppressing commerce fields on product forms.

This module owns the **mechanism** only. It does not suppress any fields itself — that is the responsibility of bridge modules (e.g. `sor_business_model_non_commercial`). It must install cleanly in isolation.

**What this module does NOT do:**
- Suppress any product form fields on its own
- Implement any commercial workflow (consignments, sales agreements, etc.)
- Provide a product-category override layer (deferred to a later sprint)

---

## Business Model field

`res.company.business_model` is a `Selection` field set at the company level.

- **Where to set it:** General Settings → **Business Model** section (positioned below the Companies section)
- **Default value:** `non_commercial`
- **Required:** Yes — every company always has a model set
- **Extended by:** Bridge modules add new values via `selection_add`

### Built-in selection values (Sprint 07)

| Value | Label | Meaning |
|-------|-------|---------|
| `non_commercial` | Non-Commercial | Default. Suppresses all pricing UI — no sales price, no Can be Sold, no Sales tab. Used by permanent collections (e.g. SETU). |
| `primary_market_gallery` | Primary Market Gallery | Commercial gallery selling works by living artists via consignment. Revenue model: consignment splits. |
| `secondary_market_gallery` | Secondary Market Gallery | Commercial gallery trading in resale works. Revenue model: vendor commission on resale. |
| `auction_house` | Auction House | Runs timed sale events with lot catalogues. Revenue model: buyer's premium and seller's fee. |

All four values are defined in `sor_business_model/models/res_company.py`. Bridge modules that implement commerce suppression for a specific value (e.g. `sor_business_model_non_commercial`) depend on `sor_business_model` and use `selection_add` only if they need to extend beyond these four.

---

## Field Key vocabulary

The suppression vocabulary is defined in `sor_business_model/models/const.py` as `SUPPRESSIBLE_FIELDS`. Bridge modules must use these keys when creating rule records.

| field_key | UI element |
|---|---|
| `can_be_sold` | Can be Sold toggle on product form |
| `sale_price_field` | Sales Price (list_price) field on product form |
| `cost_field` | Cost (standard_price) field on product form |
| `sales_tab` | Sales tab on product form |
| `can_be_purchased` | Can be Purchased toggle on product form |
| `purchase_tab` | Purchase tab on product form |

---

## sor.business.model.rule

Each row in this model declares that a specific `field_key` should be suppressed when the active company's `business_model` matches `business_model` on the rule.

| Field | Type | Description |
|---|---|---|
| `business_model` | Char | The business model value this rule applies to (e.g. `'non_commercial'`) |
| `field_key` | Selection | Key from `SUPPRESSIBLE_FIELDS` vocabulary |
| `active` | Boolean | `string='Suppressed'`. `True` = field is suppressed. `False` = field is visible. |
| `description` | Char | Human-readable note for the developer menu |

### The `active` flag and the developer list

`active` is Odoo's standard archive field. When `active=False`, the record is excluded from all default searches. The Business Model Rules list action uses `context={'active_test': False}` so **all rules** — including unsuppressed ones — remain visible in the developer menu regardless of their `active` state.

---

## is_field_suppressed(field_key)

Method on `product.template`. Returns `True` if an active rule exists for the product's effective business model and the given field key.

```python
rec.is_field_suppressed('sale_price_field')  # → True or False
```

**Returns `False` when:**
- No active rule exists for the current model and field key
- The company has no business model set (empty string)

**Performance:** Uses `search_count` with indexed fields — a fast single-integer lookup, no records loaded.

---

## effective_business_model

A `store=False` computed field on `product.template`. Returns `env.company.business_model` — the current company's business model.

```python
rec.effective_business_model  # → 'non_commercial' (or other value)
```

**Page refresh required:** This field reads `env.company` at the time the form is loaded. After changing the company's business model in Settings, a hard browser refresh (Cmd+Shift+R / Ctrl+Shift+R) is required before the change takes effect on open product forms.

---

## Building a bridge module

Follow `sor_business_model_non_commercial` as the canonical example.

### Steps

1. **Create the module** with `depends=['sor_business_model']` and `auto_install=True`. The bridge activates automatically when `sor_business_model` is installed.

2. **Extend `res.company.business_model`** via `selection_add`:
   ```python
   business_model = fields.Selection(
       selection_add=[('commercial_primary', 'Commercial (Primary Market)')],
       ondelete={'commercial_primary': 'set default'},
   )
   ```

3. **Create rule data records** in `data/` XML for your new model value, using keys from `SUPPRESSIBLE_FIELDS`. Use `noupdate="1"` so developer toggles survive module upgrades.

4. **Add per-field computed booleans** to `product.template` (via `_inherit`):
   ```python
   is_sale_price_suppressed = fields.Boolean(
       compute='_compute_business_model_suppressions', store=False)

   @api.depends('effective_business_model')
   def _compute_business_model_suppressions(self):
       for rec in self:
           rec.is_sale_price_suppressed = rec.is_field_suppressed('sale_price_field')
   ```

5. **Declare the suppression booleans in the view arch** before using them in `invisible` expressions. Fields referenced in `invisible` must be present in the combined arch or the JS arch parser will crash at runtime:
   ```xml
   <!-- Declare suppression booleans so the view parser can resolve their type -->
   <xpath expr="//field[@name='name']" position="before">
       <field name="is_sale_price_suppressed" invisible="1"/>
   </xpath>
   ```

6. **Inherit product form views** using those booleans:
   ```xml
   <xpath expr="//field[@name='list_price']" position="attributes">
       <attribute name="invisible">is_sale_price_suppressed</attribute>
   </xpath>
   ```

7. One boolean per suppressed element — not a single shared catch-all boolean.

---

## Developer Rules menu

**Location:** Settings → Technical → SOR → Business Model Rules (developer mode only)

Shows all `sor.business.model.rule` records across all bridge modules. Click a row to open the form view, then uncheck **Suppressed** to re-enable that element without code changes. A hard browser refresh is required to observe the change on already-open product forms.

---

## Interoperability with sor_asset_paradigm

The two mechanisms are fully independent and stack without conflict.

| Layer | Mechanism | Scope | Example effect |
|---|---|---|---|
| Asset Paradigm | Product-level | Per `asset_paradigm` value on the product | Hides Forecasted Qty, Reorder Rules, quant columns |
| Business Model | Company-level | Per `business_model` value on the company | Hides Sales Price, Can be Sold, Sales tab |

An artwork in a non-commercial collection has both applied simultaneously.

---

## Interoperability with SOR auction modules

| Module combination | Effect |
|---|---|
| `sor_business_model` only | Business Model field on company. Suppression mechanism. No bridge-specific rules. |
| `sor_business_model` + `sor_business_model_non_commercial` | Bridge auto-installs. `non_commercial` rules active: Can be Sold, Sales Price, Sales tab suppressed. |
| `sor_business_model` + `sor_lotting` | No interaction — `sor_lotting` depends on `product`, not `sor_business_model`. |
| `sor_business_model` + `sor_events` | No interaction — `sor_events` depends on `base` and `mail`, not `sor_business_model`. |
