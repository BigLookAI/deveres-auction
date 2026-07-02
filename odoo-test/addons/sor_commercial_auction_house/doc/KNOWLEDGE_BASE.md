# sor_commercial_auction_house — Knowledge Base

## Overview

`sor_commercial_auction_house` is a bridge module that activates automatically when both `sor_business_model` and `sor_events_auction` are installed. It adds the commercial fee layer to auction house operations: a per-company fee schedule (vendor fees and buyer's premium tiers), fee cascade logic for new lots, a fee-aware break-even value computation, and product field suppression rules for the `auction_house` business model.

This is a bridge-of-bridge module. `sor_events_auction` is itself a bridge between `sor_events` and `sor_lotting`. This module sits one level deeper, crossing `sor_business_model` with that existing bridge.

**What this module does:**
- Adds `Buyer's Premium Tiers` and `Vendor Fee Schedule` sections to General Settings, visible only for `auction_house` companies
- Seeds one `sor.fee.default` per fee type and one `sor.buyers.premium.tier` per company on install
- Cascades fee rates to new lots: company default (seller's commission); company default (withdrawal fee); first tier (buyer's premium)
- Overrides `_compute_break_even_value` on `sor.lot` to use the fee-aware formula
- Installs four `sor.business.model.rule` suppression records that hide commercial product fields for `auction_house` companies
- Adds `is_commercial` toggle to auction events; hides the Fees tab on lots when the event is non-commercial
- Adds a **Seller** tab to the partner form with `default_sellers_commission_pct` — infrastructure for the future consignments bridge

**What this module does NOT do:**
- Record hammer prices, process payments, or manage bidding
- Implement tiered buyer's premium calculations (MVP: single flat tier; tiered rates are deferred)
- Suppress fees for specific lot types or product categories (per-lot override is manual)
- Enforce any constraint between `is_commercial` on the event and the lot fee fields — the Fees tab is hidden as a UI aid, but the field values are not zeroed

**Depends on:** `sor_business_model`, `sor_events_auction`

**Auto-activates with:** `sor_business_model` + `sor_events` + `sor_lotting` (because `sor_events_auction` auto-installs with `sor_events` + `sor_lotting`)

---

## Key Fields and Models

### sor.fee.default

Company-level default rates for vendor-side fees. One record per fee type per company.

| Field | Type | Description |
|-------|------|-------------|
| `company_id` | Many2one `res.company` | Required. Defaults to `env.company`. |
| `fee_type` | Selection | `sellers_commission` (Seller's Commission) or `withdrawal_fee` (Withdrawal Fee). Required. |
| `rate_pct` | Float | Default rate as a percentage. 0.0 means no fee. |

**_check_company_auto:** True — ORM validates company consistency at write.

**Multi-company:** One `ir.rule` restricts visibility to the user's accessible companies.

---

### sor.buyers.premium.tier

Per-company buyer's premium schedule. MVP: one tier per company. Sequenced for future multi-tier expansion.

| Field | Type | Description |
|-------|------|-------------|
| `company_id` | Many2one `res.company` | Required. Defaults to `env.company`. |
| `currency_id` | Many2one `res.currency` | Related to `company_id.currency_id`. Stored. Used by the Monetary widget. |
| `sequence` | Integer | Display order. Default 10. Lower sequence = higher precedence when tiers are added. |
| `threshold_from` | Monetary | Hammer price from which this tier applies. Use 0.00 for a base (catch-all) tier. |
| `rate_pct` | Float | Buyer's premium rate as a percentage. |

**_check_company_auto:** True.

**Multi-company:** One `ir.rule` restricts visibility to the user's accessible companies.

---

### res.company (extended)

| Field | Type | Description |
|-------|------|-------------|
| `fee_default_ids` | One2many `sor.fee.default` | All vendor fee defaults for this company. |
| `buyers_premium_tier_ids` | One2many `sor.buyers.premium.tier` | All buyer's premium tiers for this company. |

`create` is overridden to call `_ensure_fee_defaults` and `_ensure_buyers_premium_tier` whenever a new company is created, so new companies are always seeded with an empty fee schedule.

---

### res.partner (extended)

| Field | Type | Description |
|-------|------|-------------|
| `default_sellers_commission_pct` | Float | Per-consignor default seller's commission rate. Visible in the **Seller** tab on the partner form. Infrastructure for the consignments bridge — the rate is not currently wired into the lot fee cascade (consignor assignment was removed from `sor.lot` pending the consignments sprint). |

---

### sor.lot (extended)

| Field | Type | Description |
|-------|------|-------------|
| `sellers_commission_pct` | Float | Per-lot seller's commission %. Defaults from company schedule on new lot creation. |
| `withdrawal_fee_pct` | Float | Per-lot withdrawal fee %. Defaults from company schedule. Does not affect break-even. |
| `buyers_premium_pct` | Float | Per-lot buyer's premium %. Defaults from first premium tier. |
| `is_commercial_auction` | Boolean (computed, `store=False`) | True when the lot's auction has `is_commercial=True`, or (for unattached lots) when the company's `business_model == 'auction_house'`. Drives visibility of the Fees tab. |
| `break_even_value` | Monetary (computed, `store=False`) | Overrides the base `sor_lotting` computation — see formula below. |

---

### sor.event (extended)

| Field | Type | Description |
|-------|------|-------------|
| `is_commercial` | Boolean | Default `True`. When `False`, lots in this auction show no Fees tab. Used for charity or benefit auctions. Hidden on the event form when `event_type != 'auction'`. |

---

## Methods

### `default_get(fields_list)` on `sor.lot`

Called when a new lot form is opened. Populates fee rate defaults from the company fee schedule:

**Seller's commission:** The `rate_pct` of the company's `sellers_commission` fee default. If no record exists, defaults to 0.0.

**Withdrawal fee:** The `rate_pct` of the company's `withdrawal_fee` fee default. If no record exists, defaults to 0.0.

**Buyer's premium:** The `rate_pct` of the first (lowest `sequence`) tier in `buyers_premium_tier_ids`. If no tier exists, defaults to 0.0.

All values are written as form defaults — they can be overridden per lot without affecting the company schedule or other lots.

**Note on consignor-level cascade:** A per-consignor override level was originally planned but removed (UAT fix #22) pending the consignments bridge sprint. The `default_sellers_commission_pct` field on `res.partner` is preserved as infrastructure and will be wired into the cascade when `sor_consignments` is delivered.

---

### `_compute_break_even_value` on `sor.lot`

Overrides the base implementation in `sor_lotting`. Computes the minimum hammer price for the house to break even after paying out the seller.

**Formula:**
```
break_even_value = reserve_price / (1 - sellers_commission_pct / 100)
```

**Fallback:** When `sellers_commission_pct` is 0% or 100% (zero denominator), returns `reserve_price` unchanged.

**Dependencies:** `reserve_price`, `sellers_commission_pct`

**Example:** Reserve = £8,000, Seller's Commission = 20% → Break-even = 8,000 / 0.80 = £10,000.

---

### `_compute_is_commercial_auction` on `sor.lot`

Computed field (`store=False`). Returns:
- `auction_id.is_commercial` when a lot is assigned to an auction
- `company_id.business_model == 'auction_house'` when no auction is assigned

**Dependencies:** `auction_id`, `auction_id.is_commercial`, `company_id.business_model`

---

## Configuration

### Setting the fee schedule

**Navigation:** General Settings → **Buyer's Premium** block (and **Vendor Fee Schedule** block)

These blocks are only visible when the active company's **Business Model** is set to `Auction House`. If you do not see them, check Settings → **Business Model** first.

| Block | What to configure | Effect |
|-------|-------------------|--------|
| Buyer's Premium Tiers | One row per tier — Hammer Price From and Rate % | New lots default `buyers_premium_pct` from the first (lowest sequence) tier |
| Vendor Fee Schedule | Seller's Commission row and Withdrawal Fee row | New lots default their rates from these rows |

Save with the main **Save** button. Changes take effect on lots created after saving.

### Setting a per-consignor rate (infrastructure — not yet active)

**Navigation:** Contacts → open any partner → **Seller** tab → **Default Seller's Commission %**

This field is available for data entry but is not currently used in the lot fee cascade. It will be activated when the `sor_consignments` bridge is delivered. Set a value here to pre-populate it ready for when the cascade is live.

### Configuring the `is_commercial` toggle

**Navigation:** Auction Events list → open an event → **Commercial Auction** field (visible only when Event Type = Auction)

When unchecked, the Fees tab disappears from all lots in that auction. This does not zero out existing fee values — it only hides the tab. Suitable for benefit auctions or events where no fees apply.

---

## Developer Menu

The suppression rules installed by this module are visible in the Business Model Rules developer list.

**Navigation:** Settings → Technical → SOR → Business Model Rules (developer mode required)

Filter by Business Model = `auction_house` to see the four rules this module installs:

| Rule | field_key | Active by default |
|------|-----------|-------------------|
| Auction House: hide Can be Sold toggle | `can_be_sold` | Yes |
| Auction House: hide Sales Price field | `sale_price_field` | Yes |
| Auction House: hide Sales tab | `sales_tab` | Yes |
| Auction House: hide Prices tab | `sale_price_tab` | Yes |

To temporarily re-enable a suppressed field for debugging, click the rule row and uncheck **Suppressed**. Hard-refresh the browser. Re-check when done.

---

## Building on This Module

This module is a bridge-of-bridge and the end of its dependency chain. To extend it:

1. **Add a new fee type:** Add a new selection value to `sor.fee.default.fee_type` via `selection_add` in a further bridge, with `ondelete` policy. Add a corresponding entry to `_FEE_DEFAULTS` in `hooks.py` (or the extending module's hook) so new companies are seeded with the new type.

2. **Add a new suppression rule:** Create a `sor.business.model.rule` data record in your module's XML with `noupdate="1"`, using `business_model='auction_house'` and your chosen `field_key` from the `SUPPRESSIBLE_FIELDS` vocabulary in `sor_business_model`.

3. **Implement tiered buyer's premium:** The `sor.buyers.premium.tier` model already supports multiple tiers via `sequence` and `threshold_from`. The `default_get` currently reads only the first tier. To apply the correct tier to a lot's `buyers_premium_pct` at cataloguing time (once the hammer price is known), override `action_catalogue` on `sor.lot` in a further bridge and implement the tier lookup there.

4. **Per-product-type fee rules:** Add a second cascade level between consignor and company by inspecting the lot's `product_id.product_type` or `asset_paradigm` in `default_get`.

---

## Regression Checks

R1 — **Fee schedule blocks appear in General Settings for auction_house companies**
1. Set a company's Business Model to `Auction House` in General Settings → Business Model.
2. Scroll down. Confirm **Buyer's Premium** and **Vendor Fee Schedule** blocks are visible.
3. Change Business Model to any other value (e.g. `Non-Commercial`). Confirm both blocks disappear.

R2 — **New lot defaults from company fee schedule**
1. In General Settings, set Seller's Commission to 12% and Withdrawal Fee to 5%.
2. Open the Lot Catalogue list and create a new lot.
3. Navigate to the Fees tab. Confirm **Seller's Commission %** = 12.0 and **Withdrawal Fee %** = 5.0.
4. Confirm **Buyer's Premium %** matches the Rate % of the first Buyer's Premium tier.

R3 — **Default Seller's Commission % visible on partner Seller tab**
1. Open any contact record.
2. Confirm a **Seller** tab is visible on the partner form.
3. Navigate to the Seller tab.
4. Confirm the **Default Seller's Commission %** field is present and editable.

R4 — **Break-even formula**
1. On a lot with Reserve Price = 8,000 and Seller's Commission = 20%, confirm **Break-Even Value** = 10,000.
2. Change Seller's Commission to 0%. Confirm Break-Even Value = Reserve Price.
3. Change Reserve Price to 12,000 with Seller's Commission = 25%. Confirm Break-Even Value = 16,000.

R5 — **Per-lot override does not affect other lots**
1. Create two lots (A and B) with the same company defaults.
2. Change Seller's Commission % on Lot A to 30%.
3. Confirm Lot B's Seller's Commission % is unchanged.
4. Confirm the company fee schedule is unchanged (General Settings → Vendor Fee Schedule).

R6 — **is_commercial toggle hides Fees tab**
1. Open an auction event and uncheck **Commercial Auction**.
2. Open a lot assigned to that auction. Confirm the **Fees** tab is not visible.
3. Return to the event and re-check **Commercial Auction**.
4. Confirm the Fees tab reappears on the lot (may require page refresh).

R7 — **Product fields suppressed for auction_house companies**
1. Set company Business Model to `Auction House`.
2. Open any product template. Confirm **Can be Sold**, **Sales Price**, Sales tab, and Prices tab are all absent.
3. Set Business Model to `Primary Market Gallery`. Confirm the fields reappear.

R8 — **Two events (commercial and non-commercial) coexist**
1. Create Event A with `is_commercial = True` and Event B with `is_commercial = False`.
2. Create a lot and assign it to Event A. Confirm Fees tab is visible.
3. Reassign the lot to Event B. Confirm Fees tab is hidden.
4. Confirm the lot's fee field values are retained (not zeroed) after reassignment.

---

## Interoperability

| Module combination | Effect |
|---|---|
| `sor_business_model` only | Business Model field on company. Suppression mechanism. No auction-specific rules. |
| `sor_events_auction` only | Lots can be assigned to auction events. No fee fields on lots. |
| `sor_business_model` + `sor_events_auction` | This bridge auto-installs. Fee schedule, cascade logic, break-even formula, suppression rules for `auction_house`. |
| Bridge + `sor_asset_paradigm_artwork` | Fee fields and artwork paradigm suppression stack independently. Both apply to artwork lots in an auction house. |
| Bridge + `sor_business_model_non_commercial` | Both sets of suppression rules are active. A non-commercial company still has no fee fields on lots (bridge is present but `is_commercial_auction` is False for all lots). |
