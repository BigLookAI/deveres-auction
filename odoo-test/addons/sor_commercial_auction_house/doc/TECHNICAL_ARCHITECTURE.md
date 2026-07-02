# Technical Architecture: sor_commercial_auction_house

## Overview

`sor_commercial_auction_house` is a **bridge-of-bridge module** that delivers the commercial fee layer for auction house operations. It sits at the intersection of `sor_business_model` (company-level commerce model) and `sor_events_auction` (the auction event and lot bridge). Neither parent is modified; the bridge activates automatically when both are present.

```
sor_business_model          sor_events_auction
        \                         /
         \                       /
    sor_commercial_auction_house   (auto_install=True, application=False)
```

`sor_events_auction` is itself a bridge between `sor_events` and `sor_lotting`. The full dependency chain is therefore:

```
sor_business_model   sor_events   sor_lotting
        \                \         /
         \           sor_events_auction
          \               /
     sor_commercial_auction_house
```

This module introduces two new models (`sor.fee.default`, `sor.buyers.premium.tier`), extends `res.company`, `res.partner`, `sor.lot`, and `sor.event`, and installs four business model suppression rules for the `auction_house` model value.

---

## Module Pattern

**Manifest flags:**

```python
'category': 'Hidden/Technical',
'depends': ['sor_business_model', 'sor_events_auction'],
'auto_install': True,
'application': False,
'post_init_hook': 'post_init_hook',
```

- `auto_install: True` — Odoo installs the bridge automatically when both `sor_business_model` and `sor_events_auction` are present. Because `sor_events_auction` itself is `auto_install`, this bridge activates whenever `sor_business_model` + `sor_events` + `sor_lotting` are all installed.
- `application: False` — Not shown as a top-level App.
- `category: 'Hidden/Technical'` — Excluded from business category listings.
- `post_init_hook: 'post_init_hook'` — Required to seed fee records for all companies present at install time. Without this, a company that existed before the bridge was installed would have no fee defaults, causing `default_get` to return 0.0 silently.

**Why a bridge?** Fee schedule and break-even logic require knowledge of the company's business model (`sor_business_model`) and the lot model (`sor_lotting`, accessed via `sor_events_auction`). Neither parent can declare a dependency on the other without violating the SOR composability constraint. The bridge carries the coupling exclusively.

---

## Architecture Decisions

### 1. Two new models rather than extending sor.lot directly

Fee schedule data (default rates) and per-lot fee data are different concerns at different cardinalities. A company has two fee defaults and one (or more) premium tiers; a lot has three fee fields. Storing company defaults in new first-class models (`sor.fee.default`, `sor.buyers.premium.tier`) with `company_id` gives:
- Standard multi-company scoping with `ir.rule`
- Settings UI via related fields on `res.config.settings`
- A foundation for future multi-tier premium logic (adding tiers, not model changes)

Storing defaults as flat fields on `res.company` would conflate company configuration with the multi-company isolation pattern and would not scale to tiered rates.

### 2. `default_get` override for cascade, not `@api.onchange`

Fee cascade happens in `default_get` so that defaults populate when the form opens — before the user interacts. `default_get` is the correct Odoo mechanism for initial field values derived from external state (the company fee schedule). The cascade currently reads from the company schedule only. A per-consignor override level was planned but removed (UAT fix #22) — the `default_sellers_commission_pct` on `res.partner` exists as infrastructure and will be wired in when `sor_consignments` delivers the consignor assignment model.

### 3. `_compute_break_even_value` override pattern in Odoo 19

`sor_lotting` defines `_compute_break_even_value` with `@api.depends('reserve_price')`. This bridge redefines the same method in an `_inherit = 'sor.lot'` class with an extended `@api.depends` signature (`reserve_price`, `sellers_commission_pct`). In Odoo 19, when two modules both define `_compute_break_even_value` on the same model via `_inherit`, the last-loaded method wins (Python's MRO for Odoo model classes). The bridge is loaded after `sor_lotting` in the module graph, so the bridge's implementation takes precedence. No `super()` call is made — the base implementation (simple pass-through to `reserve_price`) is intentionally replaced.

**Risk:** Any future `_inherit = 'sor.lot'` that also overrides `_compute_break_even_value` would silently replace this bridge's formula. Convention: extensions to break-even logic must be implemented via a bridge that declares this module as a dependency, not by re-overriding the method in an independent module.

### 4. `is_commercial_auction` as a `store=False` computed field

The Fees tab visibility depends on `auction_id.is_commercial` and `company_id.business_model`. Both are context-dependent values that can change at runtime (users can toggle `is_commercial` on an event; a company's business model can be changed in settings). A `store=True` computed field would go stale. The field is declared `store=False` to always read live state.

This field cannot be used in a search domain for list filtering. If list filtering by commercial status is needed in future, a `_search` method must be added.

### 5. Suppression rules use the `sor_business_model` vocabulary

The four suppression rules installed by this module use `field_key` values from `sor_business_model/models/const.py` (`SUPPRESSIBLE_FIELDS`). The actual view inheritance that hides those fields is implemented in `sor_business_model_non_commercial` (and re-used here because the same computed suppression booleans on `product.template` cover both the `non_commercial` and `auction_house` business models). No new view inheritance is needed in this bridge — the suppression mechanism in `sor_business_model` already reads active rules for the current company's model.

### 6. `noupdate="1"` on suppression rules and multi-company record rules

Both the suppression rule data records and the `ir.rule` security records use `noupdate="1"`. This prevents module upgrades from overwriting:
- Developer toggles on suppression rules (unchecking a rule via the developer menu)
- Administrator customisations to the record rule domain in production

### 7. `sale_price_tab` in the suppression vocabulary

The `sale_price_tab` `field_key` (which hides the Prices tab on product forms) is included as a fourth suppression rule alongside the three from `sor_business_model_non_commercial`. This was confirmed at Show & Tell: in an auction house deployment, pricing information on product forms is redundant because commercial terms live on the lot record.

---

## Models

### sor.fee.default (new model)

**File:** `models/sor_fee_default.py`

| Field | Type | Notes |
|-------|------|-------|
| `company_id` | Many2one `res.company` | Required. Default `env.company`. `_check_company_auto = True`. |
| `fee_type` | Selection | `sellers_commission`, `withdrawal_fee`. Required. |
| `rate_pct` | Float | Default rate percentage. |

**`_order`:** `company_id, fee_type`

No methods. Data records only — read by `default_get` and displayed in Settings.

---

### sor.buyers.premium.tier (new model)

**File:** `models/sor_buyers_premium_tier.py`

| Field | Type | Notes |
|-------|------|-------|
| `company_id` | Many2one `res.company` | Required. Default `env.company`. `_check_company_auto = True`. |
| `currency_id` | Many2one `res.currency` | Related to `company_id.currency_id`. `store=True`. Required by Monetary widget. |
| `sequence` | Integer | Default 10. Lower = higher precedence for future multi-tier logic. |
| `threshold_from` | Monetary | `currency_field='currency_id'`. `0.00` = base tier (all hammer prices). |
| `rate_pct` | Float | Rate percentage for this tier. |

**`_order`:** `company_id, sequence`

No methods.

---

### res.company (extended)

**File:** `models/res_company.py`

| Addition | Type | Notes |
|----------|------|-------|
| `fee_default_ids` | One2many `sor.fee.default` / `company_id` | Vendor fee schedule for this company. |
| `buyers_premium_tier_ids` | One2many `sor.buyers.premium.tier` / `company_id` | Premium tiers for this company. |
| `create` override | `@api.model_create_multi` | Calls `hooks._ensure_fee_defaults` and `hooks._ensure_buyers_premium_tier` for each new company. |

The `create` override imports `hooks` from the package root and calls the private helper functions directly. This ensures the same idempotent seeding logic is used at install time (via `post_init_hook`) and at runtime (via `create`).

---

### res.partner (extended)

**File:** `models/res_partner.py`

| Addition | Type | Notes |
|----------|------|-------|
| `default_sellers_commission_pct` | Float | Consignor override rate. Zero = use company default. |

No methods. Read by `default_get` on `sor.lot`.

---

### sor.lot (extended)

**File:** `models/sor_lot_commercial.py`

| Addition | Type | Notes |
|----------|------|-------|
| `is_commercial_auction` | Boolean computed | `store=False`. Depends on `auction_id.is_commercial` and `company_id.business_model`. |
| `sellers_commission_pct` | Float | Per-lot seller's commission. Defaulted from company schedule via `default_get`. |
| `withdrawal_fee_pct` | Float | Per-lot withdrawal fee. Does not affect break-even. |
| `buyers_premium_pct` | Float | Per-lot buyer's premium. |
| `_compute_break_even_value` | Method | Overrides `sor_lotting`. Formula: `reserve / (1 - commission/100)`. Falls back to `reserve_price` when commission is 0% or 100%. |
| `default_get` | Method | Overrides `models.Model`. Implements the three-level fee cascade (see Architecture Decisions §2). |

**`@api.depends` on `_compute_break_even_value`:** `('reserve_price', 'sellers_commission_pct')` — extends the base dependency on `reserve_price` by adding `sellers_commission_pct`.

---

### sor.event (extended)

**File:** `models/sor_event_commercial.py`

| Addition | Type | Notes |
|----------|------|-------|
| `is_commercial` | Boolean | Default `True`. Controls Fees tab visibility on lots in this auction via `is_commercial_auction`. |

---

### res.config.settings (extended)

**File:** `models/res_config_settings.py`

| Addition | Type | Notes |
|----------|------|-------|
| `fee_default_ids` | One2many related | `related='company_id.fee_default_ids'`, `readonly=False`. Exposes fee schedule in Settings. |
| `buyers_premium_tier_ids` | One2many related | `related='company_id.buyers_premium_tier_ids'`, `readonly=False`. Exposes premium tiers in Settings. |

---

## Views

### res.config.settings (General Settings)

**File:** `views/res_config_settings_views.xml`

Inherits `base_setup.res_config_settings_view_form`. Adds two `<block>` sections immediately after `sor_business_model.sor_business_model_setting_container` (the Business Model selector block):

| Block | `invisible` condition | Contents |
|-------|----------------------|----------|
| `sor_buyers_premium_setting_container` | `business_model != 'auction_house'` | Editable list of `buyers_premium_tier_ids` |
| `sor_vendor_fee_setting_container` | `business_model != 'auction_house'` | Editable list of `fee_default_ids` |

The `business_model` field is already declared in the arch by `sor_business_model` — no redeclaration needed in this view. Using the XPath anchor `//block[@name='sor_business_model_setting_container']` + `position="after"` inserts the fee blocks directly below the Business Model selector, giving the user a logical top-to-bottom flow: set model → configure fees.

The buyers_premium list includes `<field name="currency_id" column_invisible="1"/>` to satisfy the Monetary widget's currency resolution without rendering a column header.

### sor.lot (Fees tab)

**File:** `views/sor_lot_commercial_views.xml`

Inherits `sor_lotting.sor_lot_view_form` (the base lot form view).

**XPath 1:** Inserts `<field name="is_commercial_auction" invisible="1"/>` before `<notebook>`. Required by Odoo 19's `FormArchParser` — fields referenced in `invisible` expressions must be declared in the combined arch, or the JS view parser raises "Cannot read properties of undefined (reading 'type')".

**XPath 2:** Appends a `<page string="Fees" invisible="not is_commercial_auction">` inside the notebook. The page contains:
- **Consignor group:** `consignor_id` field
- **Fee Rates group:** `sellers_commission_pct`, `withdrawal_fee_pct`, `buyers_premium_pct`
- **Break-Even group:** `break_even_value` (monetary, readonly)

**Partner form view patch:** A separate record adds a new **Seller** tab to `base.view_partner_form` containing the `default_sellers_commission_pct` field. The tab is always visible when this bridge is installed (auction house deployments only).

### sor.event (is_commercial toggle)

**File:** `views/sor_event_commercial_views.xml`

Inherits `sor_events.sor_event_view_form`. Inserts `is_commercial` field immediately after `event_type`, with `invisible="event_type != 'auction'"`. The toggle is contextually hidden for non-auction events where it has no meaning.

---

## Module File Structure

```
addons/sor_commercial_auction_house/
├── __init__.py                                    # imports models and post_init_hook
├── __manifest__.py                                # depends=['sor_business_model','sor_events_auction'], auto_install=True
├── hooks.py                                       # post_init_hook, _ensure_fee_defaults, _ensure_buyers_premium_tier
├── models/
│   ├── __init__.py
│   ├── res_company.py                             # fee_default_ids, buyers_premium_tier_ids One2many; create override
│   ├── res_config_settings.py                     # related fields for Settings UI
│   ├── res_partner.py                             # default_sellers_commission_pct Float
│   ├── sor_buyers_premium_tier.py                 # New model: tiered buyer's premium schedule
│   ├── sor_event_commercial.py                    # is_commercial Boolean on sor.event
│   ├── sor_fee_default.py                         # New model: vendor fee defaults
│   └── sor_lot_commercial.py                      # Fee fields, default_get cascade, break-even override
├── views/
│   ├── res_config_settings_views.xml              # Fee schedule blocks in General Settings
│   ├── sor_event_commercial_views.xml             # is_commercial toggle on event form
│   └── sor_lot_commercial_views.xml               # Fees tab on lot form; partner commission field
├── data/
│   └── sor_commercial_auction_house_suppression_rules.xml   # 4 sor.business.model.rule records for auction_house
├── security/
│   ├── ir.model.access.csv                        # Read/write/create/delete for both new models
│   └── sor_commercial_auction_house_rules.xml     # Multi-company ir.rule for sor.fee.default and sor.buyers.premium.tier
├── i18n/
│   └── sor_commercial_auction_house.pot           # Translatable strings
├── tests/
│   ├── __init__.py
│   └── test_sor_commercial_auction_house.py       # 26 tests covering models, cascade, break-even, composability
└── doc/
    ├── KNOWLEDGE_BASE.md                          # User-facing feature documentation
    └── TECHNICAL_ARCHITECTURE.md                 # This file
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | `auto_install=True`, `depends=['sor_business_model','sor_events_auction']` — the composability declaration |
| `hooks.py` | `post_init_hook` seeds fee records for all pre-existing companies at install time |
| `models/sor_lot_commercial.py` | Fee fields, `default_get` cascade, `_compute_break_even_value` override |
| `models/res_company.py` | `create` override — ensures new companies are always seeded with fee records |
| `data/sor_commercial_auction_house_suppression_rules.xml` | Four `sor.business.model.rule` records for `auction_house` with `noupdate="1"` |
| `security/sor_commercial_auction_house_rules.xml` | Multi-company `ir.rule` for both new models with `noupdate="1"` |
| `views/sor_lot_commercial_views.xml` | Fees tab with `is_commercial_auction` arch declaration |
| `tests/test_sor_commercial_auction_house.py` | 26 tests covering module installs, seeding, cascade, break-even, composability |

---

## Composability Boundary

| Module combination | Fee fields on lot | Fee schedule in Settings | Break-even uses commission | Suppression rules for auction_house |
|---|---|---|---|---|
| `sor_business_model` only | ✗ absent | ✗ absent | ✗ base formula (reserve only) | ✗ absent |
| `sor_events_auction` only | ✗ absent | ✗ absent | ✗ base formula | ✗ absent |
| Both parents installed | ✓ present (bridge auto-activates) | ✓ present | ✓ fee-aware formula | ✓ installed |

The composability boundary is verified by automated tests 23–26.

---

## Special Concerns

### `default_get` cascade scope

The `default_get` override on `sor.lot` reads only the company fee schedule. A consignor-level cascade was originally planned but removed at UAT (fix #22) because `consignor_id` on `sor.lot` is architecturally incorrect as a standalone field — consignor assignment belongs to the `sor_consignments` bridge. The `default_sellers_commission_pct` field on `res.partner` is preserved as infrastructure; the cascade will be extended when the consignments bridge delivers consignor assignment to `sor.lot`.

### `_compute_break_even_value` override and the MRO

Odoo builds model classes by merging all `_inherit` extensions in module dependency order. The last-defined method with a given name wins. Because `sor_commercial_auction_house` depends on `sor_events_auction` (which depends on `sor_lotting`), this bridge's `_compute_break_even_value` is loaded after `sor_lotting`'s and takes precedence without a `super()` call. The `@api.depends` signature also replaces the base signature. This is intentional and correct for Odoo 19 — the base `sor_lotting` implementation documented its own help text as a placeholder for this exact extension.

### Seeding idempotency

Both `_ensure_fee_defaults` and `_ensure_buyers_premium_tier` check for existing records before creating. They are safe to call multiple times and will not duplicate records. The `post_init_hook` and the `res.company.create` override both call these helpers, meaning any install scenario — fresh install, adding a company before the bridge, adding a company after the bridge — results in correctly seeded fee records.

### Settings visibility depends on company context

The fee schedule blocks in General Settings are hidden by `invisible="business_model != 'auction_house'"`. The `business_model` field reflects the currently selected company in Settings. A user switching the company selector in General Settings will see the blocks appear or disappear as appropriate.

### Multi-company fee isolation

Each company has its own `sor.fee.default` and `sor.buyers.premium.tier` records. The `ir.rule` on both models uses `company_ids` (the Odoo context variable containing all companies the user has access to). A user with access to multiple companies can read all their fee records but cannot read records belonging to companies they do not have access to.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 --db_user=odoo --db_password=admin \
  -d odoo -u sor_commercial_auction_house \
  --test-enable --stop-after-init
```

To run only this module's tests:

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 --db_user=odoo --db_password=admin \
  -d odoo -u sor_commercial_auction_house \
  --test-tags=post_install --stop-after-init
```

---

## Story Reference

Parent story: `.backlog/current/Auction Engine/stories/`

Sprint: Auction Engine
